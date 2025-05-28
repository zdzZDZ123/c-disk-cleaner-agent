#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
扫描模块 - 负责扫描C盘文件并收集信息
"""

import os
import time
import uuid
import hashlib  # Import hashlib for hashing
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Generator, Optional
import threading
import queue
from loguru import logger

from data.models import FileItem, ScanResult, FileType, CleanCategory
from config.manager import ConfigManager


class Scanner:
    """文件扫描器类，负责扫描C盘文件"""
    
    def __init__(self, config_manager=None, process_delay=0):
        """初始化扫描器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
            process_delay: 处理每个文件的延迟（秒），用于测试
        """
        self.config = config_manager or ConfigManager()
        self.current_scan: Optional[ScanResult] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._file_queue = queue.Queue()
        self._is_scanning = False
        self._scan_thread = None
        self._process_thread = None
        self._file_hashes: Dict[str, List[str]] = {}  # Store hashes {hash: [paths]}
        self._file_hashes_lock = threading.Lock()
        self.process_delay = process_delay
        
    def start_scan(self, scan_paths=None, exclude_paths=None) -> str:
        """启动新的扫描任务
        
        Args:
            scan_paths: 要扫描的路径列表，如果为None则使用配置中的默认路径
            exclude_paths: 要排除的路径列表，如果为None则使用配置中的默认排除路径
            
        Returns:
            扫描任务ID
        """
        if self._is_scanning:
            logger.warning("已有扫描任务正在运行，请先停止当前扫描")
            return ""
        
        # Reset internal state
        self._stop_event.clear()
        self._pause_event.clear()
        self._file_hashes = {}
        
        # 如果未提供路径，则使用配置中的默认路径
        if scan_paths is None:
            # 动态获取用户目录作为默认扫描路径
            import os
            default_user_dir = os.path.expanduser('~')
            scan_paths = self.config.get('scanner.include_dirs', [default_user_dir])
        
        if exclude_paths is None:
            # 动态获取系统目录作为默认排除路径
            import os
            system_drive = os.environ.get('SystemDrive', 'C:')
            default_exclude = [
                os.path.join(system_drive, os.sep, 'Windows'),
                os.path.join(system_drive, os.sep, 'Program Files'),
                os.path.join(system_drive, os.sep, 'Program Files (x86)')
            ]
            exclude_paths = self.config.get('scanner.exclude_dirs', default_exclude)
        
        # 初始化新的扫描结果
        scan_id = str(uuid.uuid4())
        self.current_scan = ScanResult(
            scan_id=scan_id,
            start_time=datetime.now(),
            scan_paths=scan_paths,
            exclude_paths=exclude_paths,
            is_complete=False
        )
        
        # 启动扫描线程
        self._is_scanning = True
        self._scan_thread = threading.Thread(
            target=self._scan_worker, 
            args=(scan_paths, exclude_paths)
        )
        self._scan_thread.daemon = True
        self._scan_thread.start()
        
        # 启动处理线程
        self._process_thread = threading.Thread(
            target=self._process_worker
        )
        self._process_thread.daemon = True
        self._process_thread.start()
        
        logger.info(f"开始新扫描任务 {scan_id}")
        return scan_id
    
    def stop_scan(self) -> bool:
        """停止当前扫描任务
        
        Returns:
            是否成功停止
        """
        if not self._is_scanning:
            return False
        
        logger.info("正在停止扫描任务...")
        self._stop_event.set()
        
        # 等待线程结束
        if self._scan_thread and self._scan_thread.is_alive():
            self._scan_thread.join(timeout=5.0)
        
        if self._process_thread and self._process_thread.is_alive():
            self._process_thread.join(timeout=5.0)
        
        # 完成扫描结果
        if self.current_scan:
            self.current_scan.end_time = datetime.now()
            self.current_scan.is_complete = False  # 标记为非正常完成
        
        self._is_scanning = False
        logger.info("扫描任务已停止")
        return True
    
    def pause_scan(self) -> bool:
        """暂停当前扫描任务
        
        Returns:
            是否成功暂停
        """
        if not self._is_scanning:
            return False
        
        self._pause_event.set()
        logger.info("扫描任务已暂停")
        return True
    
    def resume_scan(self) -> bool:
        """恢复当前扫描任务
        
        Returns:
            是否成功恢复
        """
        if not self._is_scanning:
            return False
        
        self._pause_event.clear()
        logger.info("扫描任务已恢复")
        return True
    
    def get_progress(self) -> Tuple[int, int, float]:
        """获取当前扫描进度
        
        Returns:
            (已处理文件数, 总大小(字节), 完成百分比)
        """
        if not self.current_scan:
            return 0, 0, 0.0
        
        total_items = self.current_scan.total_items
        total_size = self.current_scan.total_size
        
        # 估算进度，这里只是一个粗略估计
        # 实际应用中可能需要更复杂的进度计算逻辑
        progress = 0.0
        if self._is_scanning:
            # 如果仍在扫描中，根据已扫描的路径数估计进度
            if self.current_scan.scan_paths:
                scanned_paths = len([p for p in self.current_scan.scan_paths if os.path.exists(p)])
                total_paths = len(self.current_scan.scan_paths)
                if total_paths > 0:
                    progress = min(0.99, scanned_paths / total_paths)
        else:
            # 如果扫描完成，进度为100%
            progress = 1.0 if self.current_scan.is_complete else 0.0
        
        return total_items, total_size, progress
    
    def is_scanning(self) -> bool:
        """检查扫描器是否正在扫描"""
        return self._is_scanning

    def get_current_result(self) -> Optional[ScanResult]:
        """获取当前扫描结果
        
        Returns:
            当前扫描结果或None
        """
        return self.current_scan
    
    def _scan_worker(self, scan_paths: List[str], exclude_paths: List[str]):
        """扫描工作线程
        
        Args:
            scan_paths: 要扫描的路径列表
            exclude_paths: 要排除的路径列表
        """
        try:
            for path in scan_paths:
                if self._stop_event.is_set():
                    break
                    
                if not os.path.exists(path):
                    logger.warning(f"路径不存在，跳过: {path}")
                    continue
                
                logger.info(f"开始扫描路径: {path}")
                
                # 遍历路径并添加文件到队列
                for file_path, file_stat in self._walk_directory(path, exclude_paths):
                    if self._stop_event.is_set():
                        break
                        
                    # 如果暂停，等待恢复
                    while self._pause_event.is_set() and not self._stop_event.is_set():
                        time.sleep(0.5)
                    
                    # 将文件信息添加到处理队列
                    self._file_queue.put((file_path, file_stat))
            
            # 标记队列结束
            self._file_queue.put(None)
            logger.info("扫描工作线程完成")
            
        except Exception as e:
            logger.exception(f"扫描过程出错: {e}")
            self._file_queue.put(None)  # 确保处理线程能够退出
    
    def _process_worker(self):
        """文件处理工作线程，处理扫描到的文件信息"""
        try:
            while not self._stop_event.is_set():
                # 检查是否需要暂停
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                # 从队列获取文件信息
                item = None
                try:
                    item = self._file_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                if item is None:
                    break  # 队列结束标记
                
                file_path, file_stat = item
                
                # 处理文件信息
                file_item = self._process_file(file_path, file_stat)
                
                # 更新扫描结果
                if file_item and self.current_scan:
                    self.current_scan.files.append(file_item)
                    self.current_scan.total_items += 1
                    self.current_scan.total_size += file_item.size
                    
                    # 更新分类统计
                    category = file_item.category
                    if category in self.current_scan.by_category:
                        self.current_scan.by_category[category] += file_item.size
                    else:
                        self.current_scan.by_category[category] = file_item.size
                        
                    # Calculate and store hash for duplicate detection (only for regular files)
                    if file_item.type == FileType.REGULAR:
                        self._calculate_and_store_hash(file_item)
                # 处理完每个文件后增加延迟，便于测试暂停/停止
                if self.process_delay > 0:
                    time.sleep(self.process_delay)
                # 再次检查是否需要暂停
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                
            # After processing all files, identify duplicate sets
            self._find_duplicate_sets()
                
            # 标记扫描完成
            if self.current_scan and not self._stop_event.is_set():
                self.current_scan.end_time = datetime.now()
                self.current_scan.is_complete = True
                
            logger.info("文件处理工作线程完成")
            
        except Exception as e:
            logger.exception(f"文件处理过程出错: {e}")
        finally:
            self._is_scanning = False
    
    def _walk_directory(self, root_path: str, exclude_paths: List[str]) -> Generator[Tuple[str, os.stat_result], None, None]:
        """遍历目录并生成文件路径和状态
        
        Args:
            root_path: 要遍历的根路径
            exclude_paths: 要排除的路径列表
            
        Yields:
            (文件路径, 文件状态) 元组
        """
        max_depth = self.config.get('scanner.max_depth', 10)
        follow_links = self.config.get('scanner.follow_links', False)
        skip_hidden = self.config.get('scanner.skip_hidden', True)
        recursive = self.config.get('scanner.recursive', True)
        
        # 规范化排除路径
        normalized_excludes = set(os.path.normpath(os.path.abspath(p)) for p in exclude_paths)
        
        def _is_excluded(path):
            """检查路径是否应该被排除"""
            norm_path = os.path.normpath(os.path.abspath(path))
            
            # 检查是否在排除列表中
            for exclude in normalized_excludes:
                if norm_path == exclude or norm_path.startswith(exclude + os.sep):
                    return True
            
            # 检查是否是隐藏文件/目录
            if skip_hidden and os.path.basename(path).startswith('.'):
                return True
                
            return False
        
        def _walk_impl(current_path, current_depth=0):
            """递归遍历目录实现"""
            if current_depth > max_depth:
                logger.debug(f"达到最大递归深度，跳过: {current_path}")
                return
            
            try:
                # 列出目录内容
                logger.debug(f"正在扫描目录: {current_path}")
                for entry in os.scandir(current_path):
                    if self._stop_event.is_set():
                        break
                    
                    # 如果暂停，等待恢复
                    while self._pause_event.is_set() and not self._stop_event.is_set():
                        time.sleep(0.5)
                    
                    try:
                        # 如果是排除的路径，则跳过
                        if _is_excluded(entry.path):
                            logger.debug(f"排除路径，跳过: {entry.path}")
                            continue
                        
                        # ==== 彻底移除：跳过 Junction Points 和 Symbolic Links (可能不兼容旧Python版本) ====
                        # 由于 os.path.isjunction 在您的环境中不可用，并且 os.path.islink 在某些情况下也可能导致问题，
                        # 我们暂时移除对这些特殊文件类型的显式跳过逻辑。
                        # 在后续优化中，可以考虑使用更兼容的方式处理。
                        # =====================================================
                        
                        # 获取文件信息
                        try:
                            stat_info = entry.stat(follow_symlinks=follow_links)
                        except (PermissionError, OSError):
                            logger.debug(f"无法获取文件状态，跳过: {entry.path}")
                            continue  # 无法访问的文件，跳过
                        
                        # 生成文件信息
                        logger.debug(f"找到文件/目录: {entry.path}")
                        yield entry.path, stat_info
                        
                        # 如果是目录，并且允许递归，则继续遍历
                        if entry.is_dir(follow_symlinks=follow_links) and recursive:
                            logger.debug(f"进入子目录: {entry.path}")
                            yield from _walk_impl(entry.path, current_depth + 1)
                            
                    except (PermissionError, OSError) as e:
                        logger.debug(f"无法访问 {entry.path}: {e}")
                        continue
                    except Exception as e:
                        # 捕获其他意外异常
                        logger.error(f"遍历目录项时发生意外错误 {entry.path}: {e}", exc_info=True)
                        continue # 继续处理下一个目录项
                    
            except (PermissionError, OSError) as e:
                logger.debug(f"无法访问目录 {current_path}: {e}")
            except Exception as e:
                 # 捕获 os.scandir 以外的意外异常
                 logger.error(f"扫描目录时发生意外错误 {current_path}: {e}", exc_info=True) # Add logging with exc_info
        
        # 开始遍历
        logger.debug(f"开始遍历根路径: {root_path}")
        yield from _walk_impl(root_path)
    
    def _process_file(self, file_path: str, file_stat: os.stat_result) -> Optional[FileItem]:
        """处理文件信息，创建FileItem对象
        
        Args:
            file_path: 文件路径
            file_stat: 文件状态对象
            
        Returns:
            FileItem对象或None（如果处理失败）
        """
        try:
            path_obj = Path(file_path)
            
            # 判断文件类型
            file_type = FileType.UNKNOWN
            if path_obj.is_dir():
                file_type = FileType.DIRECTORY
            elif path_obj.is_symlink():
                file_type = FileType.SYMLINK
            elif path_obj.is_file():
                file_type = FileType.REGULAR
                
                # 进一步判断文件类型
                suffix = path_obj.suffix.lower()
                name_lower = path_obj.name.lower()
                
                # 临时文件
                if suffix in {'.tmp', '.temp', '.bak', '.old', '.orig', '.swp', '.swo'} or name_lower.startswith('~'):
                    file_type = FileType.TEMP
                # 日志文件
                elif suffix in {'.log', '.out', '.err'} or '.log.' in name_lower:
                    file_type = FileType.LOG
                # 缓存文件
                elif suffix in {'.cache', '.cached'} or name_lower in {'thumbs.db', 'desktop.ini'}:
                    file_type = FileType.CACHE
                # 下载文件
                elif suffix in {'.part', '.crdownload', '.download'}:
                    file_type = FileType.DOWNLOAD
                # 系统文件
                elif suffix in {'.dmp', '.mdmp', '.chk', '.gid'}:
                    file_type = FileType.SYSTEM
                # 备份文件
                elif suffix in {'.backup', '.bkp'}:
                    file_type = FileType.BACKUP
                # 文档文件
                elif suffix in {'.txt', '.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx'}:
                    file_type = FileType.DOCUMENT
                # 媒体文件
                elif suffix in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.mp4', '.avi', '.mov', '.mp3', '.wav'}:
                    file_type = FileType.MEDIA
                
            # 判断清理类别
            category = self._categorize_file(file_path, path_obj, file_type)
            
            # 检查只读属性
            is_readonly = False
            try:
                if os.name == 'nt':
                    import ctypes
                    FILE_ATTRIBUTE_READONLY = 0x01
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(file_path))
                    if attrs != -1 and (attrs & FILE_ATTRIBUTE_READONLY):
                        is_readonly = True
                else:
                    if not os.access(file_path, os.W_OK):
                        is_readonly = True
            except Exception as e:
                logger.debug(f"检查只读属性失败 {file_path}: {e}")
            attributes = {'readonly': is_readonly}
            logger.debug(f"文件 {file_path} 只读属性: {is_readonly}")
            
            # 根据分类添加 is_old 属性
            if category == CleanCategory.OLD_FILES:
                attributes['is_old'] = True
            else:
                attributes['is_old'] = False
            
            # 创建文件项
            file_item = FileItem(
                path=file_path,
                name=path_obj.name,
                size=file_stat.st_size,
                type=file_type,
                category=category,
                modified_time=datetime.fromtimestamp(file_stat.st_mtime),
                accessed_time=datetime.fromtimestamp(file_stat.st_atime),
                created_time=datetime.fromtimestamp(file_stat.st_ctime),
                is_hidden=path_obj.name.startswith('.'),
                can_delete=self._can_delete(file_path, file_type),
                attributes=attributes
            )
            
            # 新增：采集内容hash和摘要
            try:
                suffix = path_obj.suffix.lower()
                if suffix in {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}:
                    # 图片感知hash
                    try:
                        from PIL import Image, ImageFilter
                        import imagehash
                        with Image.open(file_path) as img:
                            file_item.content_hash = str(imagehash.phash(img))
                            # 检测图片模糊度
                            laplacian = img.convert('L').filter(ImageFilter.FIND_EDGES).getextrema()
                            blurry_score = laplacian[1] - laplacian[0]
                            # 阈值可调，低于一定值认为模糊
                            file_item.attributes['is_blurry'] = blurry_score < 10
                        file_item.content_summary = f"图片分辨率: {img.width}x{img.height}"
                    except Exception as e:
                        logger.debug(f"图片hash/摘要失败 {file_path}: {e}")
                elif suffix in {'.mp4', '.avi', '.mov', '.mkv'}:
                    # 视频hash/摘要（简化：用文件hash+时长）
                    try:
                        import cv2
                        cap = cv2.VideoCapture(file_path)
                        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1)
                        file_item.content_summary = f"视频时长: {duration:.1f}s"
                        file_item.content_hash = self._calculate_file_hash(file_path)
                        cap.release()
                    except Exception as e:
                        logger.debug(f"视频hash/摘要失败 {file_path}: {e}")
                elif suffix in {'.txt', '.md', '.log', '.csv', '.json', '.xml', '.html'}:
                    # 文本文件hash+前N字摘要
                    try:
                        file_item.content_hash = self._calculate_file_hash(file_path)
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(200)
                        file_item.content_summary = content.replace('\n', ' ')[:100] + ('...' if len(content) > 100 else '')
                    except Exception as e:
                        logger.debug(f"文档hash/摘要失败 {file_path}: {e}")
            except Exception as e:
                logger.debug(f"内容hash/摘要采集异常 {file_path}: {e}")
            # 新增：AI智能分析清理安全性
            file_item.clean_safety = self.analyze_clean_safety(file_item)
            return file_item
        except Exception as e:
            logger.debug(f"处理文件失败 {file_path}: {e}")
            return None
    
    def _calculate_file_hash(self, file_path: str, block_size=65536) -> Optional[str]:
        """计算文件的SHA256哈希值
        
        Args:
            file_path: 文件路径
            block_size: 读取块大小
            
        Returns:
            文件的哈希值或None（如果读取失败）
        """
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                while True:
                    data = f.read(block_size)
                    if not data:
                        break
                    sha256.update(data)
                    # Check for stop/pause events during hashing
                    if self._stop_event.is_set(): return None
                    while self._pause_event.is_set(): time.sleep(0.1)
            return sha256.hexdigest()
        except (IOError, OSError) as e:
            logger.debug(f"无法计算文件哈希值 {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"计算文件哈希值时出错 {file_path}: {e}")
            return None

    def _calculate_and_store_hash(self, file_item: FileItem):
        """计算并存储文件哈希值"""
        # Skip very small files or based on config
        min_size = self.config.get('scanner.duplicate_min_size_mb', 1) * 1024 * 1024
        if file_item.size < min_size:
            return
            
        file_hash = self._calculate_file_hash(file_item.path)
        
        if file_hash:
            with self._file_hashes_lock:
                if file_hash in self._file_hashes:
                    self._file_hashes[file_hash].append(file_item.path)
                else:
                    self._file_hashes[file_hash] = [file_item.path]

    def _find_duplicate_sets(self):
        """找出所有重复文件集"""
        if not self.current_scan:
            return
            
        duplicate_sets = []
        total_duplicate_size = 0
        with self._file_hashes_lock:
            for file_hash, paths in self._file_hashes.items():
                if len(paths) > 1:
                    duplicate_sets.append(paths)
                    # Try to get size for category calculation (best effort)
                    try:
                        first_file_path = paths[0]
                        first_file_size = os.path.getsize(first_file_path)
                        # Calculate size excluding the first file (to be kept)
                        total_duplicate_size += first_file_size * (len(paths) - 1)
                    except OSError as e:
                        logger.warning(f"Could not get size for duplicate file {paths[0]}: {e}")
            
        self.current_scan.duplicate_sets = duplicate_sets
        if total_duplicate_size > 0:
             self.current_scan.by_category[CleanCategory.DUPLICATE_FILES] = total_duplicate_size
             logger.info(f"发现 {len(duplicate_sets)} 组重复文件，总可清理大小: {total_duplicate_size / (1024*1024):.2f} MB")

        # 新增：图片重复/模糊识别（可选功能）
        try:
            from collections import defaultdict
            import imagehash
            from PIL import Image
            
            phash_map = defaultdict(list)
            blurry_images = []
            
            # 处理图片文件进行重复和模糊检测
            image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')
            for f in self.current_scan.files:
                if f.path.lower().endswith(image_extensions):
                    try:
                        # 计算图片的感知哈希
                        with Image.open(f.path) as img:
                            phash = str(imagehash.phash(img))
                            phash_map[phash].append(f.path)
                            
                            # 简单的模糊检测（基于图片方差）
                            gray_img = img.convert('L')
                            variance = gray_img.resize((100, 100)).getdata()
                            if len(set(variance)) < 50:  # 低方差可能表示模糊
                                blurry_images.append(f.path)
                    except Exception as img_e:
                        logger.debug(f"处理图片 {f.path} 时出错: {img_e}")
                        continue
            
            # 聚类phash相近的图片为重复组（允许1~2位误差）
            duplicate_images = []
            phash_keys = list(phash_map.keys())
            used = set()
            for i, h1 in enumerate(phash_keys):
                if h1 in used:
                    continue
                group = [phash_map[h1][0]]
                used.add(h1)
                for j in range(i+1, len(phash_keys)):
                    h2 = phash_keys[j]
                    if h2 in used:
                        continue
                    # 允许1位误差
                    if imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2) <= 1:
                        group.append(phash_map[h2][0])
                        used.add(h2)
                if len(group) > 1:
                    duplicate_images.append(group)
            
            self.current_scan.duplicate_images = duplicate_images
            self.current_scan.blurry_images = blurry_images
            
            if duplicate_images:
                logger.info(f"发现 {len(duplicate_images)} 组重复图片")
            if blurry_images:
                logger.info(f"发现 {len(blurry_images)} 张可能模糊的图片")
                
        except ImportError:
            logger.info("图片重复/模糊识别功能不可用：缺少 imagehash 或 Pillow 依赖")
            logger.info("要启用此功能，请运行: pip install imagehash Pillow")
            self.current_scan.duplicate_images = []
            self.current_scan.blurry_images = []
        except Exception as e:
            logger.warning(f"图片重复/模糊识别失败: {e}")
            self.current_scan.duplicate_images = []
            self.current_scan.blurry_images = []

    def _categorize_file(self, file_path: str, path_obj: Path, file_type: FileType) -> CleanCategory:
        """将文件分类到相应的清理类别
        
        Args:
            file_path: 文件路径字符串
            path_obj: Path对象
            file_type: 文件类型
            
        Returns:
            清理类别
        """
        # 优先判断是否是重复文件（基于已计算的hash）
        # Note: This categorization happens after hash calculation, so it won't be
        # immediately available when the FileItem is first created, but will be 
        # updated implicitly when _find_duplicate_sets updates by_category.
        # An alternative approach could be to re-categorize files after finding duplicates.
        
        # 临时文件
        temp_patterns = self.config.get(
            "rules.temp_files.patterns", 
            ["*.tmp", "*.temp", "~*", "*.bak", "*.old", "*.orig", "*.swp", "*.swo"]
        )
        if any(self._match_pattern(path_obj.name, p) for p in temp_patterns):
            return CleanCategory.TEMP_FILES
            
        # 日志文件
        if self.config.get("rules.log_files.enabled", True):
            log_patterns = self.config.get(
                "rules.log_files.patterns",
                ["*.log", "*.log.*", "*.out", "*.err"]
            )
            if any(self._match_pattern(path_obj.name, p) for p in log_patterns):
                return CleanCategory.LOG_FILES
                
        # 系统缓存文件
        if self.config.get("rules.system_cache.enabled", True):
            cache_patterns = self.config.get(
                "rules.system_cache.patterns",
                ["*.cache", "*.cached", "thumbs.db", "desktop.ini", "*.dmp", "*.mdmp"]
            )
            if any(self._match_pattern(path_obj.name, p) for p in cache_patterns):
                return CleanCategory.SYSTEM_CACHE
                
        # 下载临时文件
        if self.config.get("rules.download_temp.enabled", True):
            download_patterns = self.config.get(
                "rules.download_temp.patterns",
                ["*.part", "*.crdownload", "*.download", "*.tmp"]
            )
            if any(self._match_pattern(path_obj.name, p) for p in download_patterns):
                return CleanCategory.DOWNLOAD_TEMP
                
        # 开发工具缓存
        if self.config.get("rules.development_cache.enabled", True):
            dev_patterns = self.config.get(
                "rules.development_cache.patterns",
                ["node_modules", ".git/objects", "__pycache__", "*.pyc", "*.pyo", ".gradle/caches", ".m2/repository"]
            )
            # 检查目录名或文件名
            if any(self._match_pattern(path_obj.name, p) for p in dev_patterns):
                return CleanCategory.DEVELOPMENT_CACHE
            # 检查路径中是否包含这些模式
            if any(pattern in file_path for pattern in ["node_modules", "__pycache__", ".git", ".gradle", ".m2"]):
                return CleanCategory.DEVELOPMENT_CACHE
        
        # 浏览器缓存
        browser_paths = []
        if self.config.get("rules.browser_cache.chrome.enabled", True):
            chrome_paths = self.config.get(
                "rules.browser_cache.chrome.paths", 
                ["%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Cache"]
            )
            browser_paths.extend([os.path.expandvars(p) for p in chrome_paths])
        if self.config.get("rules.browser_cache.edge.enabled", True):
            edge_paths = self.config.get(
                "rules.browser_cache.edge.paths", 
                ["%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Cache"]
            )
            browser_paths.extend([os.path.expandvars(p) for p in edge_paths])
        if any(file_path.startswith(p) for p in browser_paths):
            return CleanCategory.BROWSER_CACHE
            
        # Windows缓存
        # 动态获取临时目录
        import os
        system_temp = os.path.join(os.environ.get('SystemDrive', 'C:'), os.sep, 'Windows', 'Temp')
        user_temp = os.environ.get('TEMP', '')
        temp_dirs = [system_temp, user_temp, 
         os.path.expandvars("%SYSTEMROOT%\\SoftwareDistribution\\Download")]

        windows_cache_paths = self.config.get(
            "rules.windows_cache.paths", 
            temp_dirs
        )
        windows_cache_paths = [os.path.expandvars(p) for p in windows_cache_paths]
        if any(file_path.startswith(p) for p in windows_cache_paths):
            return CleanCategory.WINDOWS_CACHE
            
        # 大文件
        min_large_size_mb = self.config.get("rules.large_files.min_size_mb", 1000)
        min_large_size_bytes = min_large_size_mb * 1024 * 1024
        try:
            if file_type == FileType.REGULAR and os.path.getsize(file_path) >= min_large_size_bytes:
                return CleanCategory.LARGE_FILES
        except OSError as e:
            logger.debug(f"無法獲取文件大小 {file_path}: {e}")
            
        # 旧文件
        if self.config.get("rules.old_files.enabled", False):
            days_old = self.config.get("rules.old_files.days", 365)
            try:
                mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                logger.debug(f"文件 {file_path} 修改时间: {mod_time}, 旧文件天数: {days_old}")
                if datetime.now() - mod_time > timedelta(days=days_old):
                    logger.debug(f"文件 {file_path} 被归类为旧文件")
                    return CleanCategory.OLD_FILES
            except OSError as e:
                logger.debug(f"无法获取文件时间 {file_path}: {e}")
            
        # 回收站
        # 动态检查回收站路径
        import os
        system_drive = os.environ.get('SystemDrive', 'C:')
        recycle_bin_path = os.path.join(system_drive, os.sep, '$Recycle.Bin').lower()
        if file_path.lower().startswith(recycle_bin_path):
            return CleanCategory.RECYCLE_BIN
            
        return CleanCategory.OTHER
    
    def _can_delete(self, file_path: str, file_type: FileType) -> bool:
        """检查文件是否可以安全删除
        
        Args:
            file_path: 文件路径
            file_type: 文件类型
            
        Returns:
            是否可以删除
        """
        # 动态获取系统保护的路径
        import os
        system_drive = os.environ.get('SystemDrive', 'C:')
        system_paths = [
            os.path.join(system_drive, os.sep, 'Windows'),
            os.path.join(system_drive, os.sep, 'Program Files'),
            os.path.join(system_drive, os.sep, 'Program Files (x86)'),
            os.path.expandvars("%SystemRoot%"),
            os.path.expandvars("%ProgramFiles%"),
        ]
        
        for sys_path in system_paths:
            if file_path.startswith(sys_path):
                return False
        
        # 如果是目录，需要更谨慎
        if file_type == FileType.DIRECTORY:
            # 重要的用户目录不应该删除
            important_dirs = [
                os.path.expandvars("%USERPROFILE%\\Documents"),
                os.path.expandvars("%USERPROFILE%\\Pictures"),
                os.path.expandvars("%USERPROFILE%\\Desktop"),
                os.path.expandvars("%USERPROFILE%\\Music"),
                os.path.expandvars("%USERPROFILE%\\Videos"),
            ]
            
            for imp_dir in important_dirs:
                if file_path == imp_dir:
                    return False
        
        # 检查是否为系统关键文件
        critical_files = [
            'ntldr', 'bootmgr', 'pagefile.sys', 'hiberfil.sys',
            'swapfile.sys', 'boot.ini', 'ntdetect.com'
        ]
        
        if file_path.name.lower() in critical_files:
            return False
            
        # 检查是否为正在使用的文件
        try:
            # 尝试以独占模式打开文件，如果失败说明文件正在使用
            with open(file_path, 'r+b'):
                pass
        except (PermissionError, OSError):
            # 文件正在使用或无权限访问
            return False
        
        return True
    
    def _match_pattern(self, file_name: str, pattern: str) -> bool:
        """检查文件名是否匹配模式
        
        支持简单的通配符匹配: * 表示任意多个字符，? 表示一个字符
        
        Args:
            file_name: 文件名
            pattern: 匹配模式
            
        Returns:
            是否匹配
        """
        # 将模式转换为正则表达式
        import re
        regex_pattern = pattern.replace(".", "\\.")
        regex_pattern = regex_pattern.replace("*", ".*")
        regex_pattern = regex_pattern.replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"
        
        # 使用正则表达式匹配
        return bool(re.match(regex_pattern, file_name))

    def analyze_clean_safety(self, file_item: FileItem) -> str:
        """AI智能分析文件清理安全性: safe(可自动清理)/confirm(需手动确认)/forbid(禁止清理)"""
        # 禁止清理：只读、不可删除、系统文件、符号链接、未知类型、系统关键文件、系统盘根目录下的文件
        if file_item.type in [FileType.SYSTEM, FileType.SYMLINK, FileType.UNKNOWN]:
            return "forbid"
        if not file_item.can_delete or file_item.attributes.get('readonly', False):
            return "forbid"
        # 系统关键文件名
        critical_files = [
            'ntldr', 'bootmgr', 'pagefile.sys', 'hiberfil.sys',
            'swapfile.sys', 'boot.ini', 'ntdetect.com'
        ]
        if file_item.name.lower() in critical_files:
            return "forbid"
        # 系统盘根目录下的文件
        system_drive = os.environ.get('SystemDrive', 'C:')
        if os.path.dirname(file_item.path.rstrip(os.sep)) == system_drive + os.sep:
            return "forbid"
        # 重要用户目录
        user_dirs = [
            os.path.expandvars("%USERPROFILE%\\Documents"),
            os.path.expandvars("%USERPROFILE%\\Pictures"),
            os.path.expandvars("%USERPROFILE%\\Desktop"),
            os.path.expandvars("%USERPROFILE%\\Music"),
            os.path.expandvars("%USERPROFILE%\\Videos"),
            os.path.expandvars("%USERPROFILE%\\Downloads"),
        ]
        for d in user_dirs:
            if file_item.path.startswith(d):
                return "confirm"
        # 超大文件（>10GB）强制手动确认
        if file_item.size >= 10 * 1024 * 1024 * 1024:
            return "confirm"
        # 最近30天内修改的文件强制手动确认
        if (datetime.now() - file_item.modified_time).days < 30:
            return "confirm"
        # 可自动清理：临时文件、缓存、回收站、重复文件、浏览器缓存、Windows缓存
        if file_item.category in [
            CleanCategory.TEMP_FILES, CleanCategory.CACHE, CleanCategory.RECYCLE_BIN,
            CleanCategory.DUPLICATE_FILES, CleanCategory.BROWSER_CACHE, CleanCategory.WINDOWS_CACHE
        ]:
            return "safe"
        # 需手动确认：大文件、旧文件、文档/媒体/下载/备份/日志
        if file_item.category in [
            CleanCategory.LARGE_FILES, CleanCategory.OLD_FILES
        ] or file_item.type in [FileType.DOCUMENT, FileType.MEDIA, FileType.BACKUP, FileType.LOG, FileType.DOWNLOAD]:
            return "confirm"
        # 其他默认需手动确认
        return "confirm"

    def get_auto_clean_list(self) -> List[FileItem]:
        """获取可自动清理的文件列表（clean_safety == 'safe'）"""
        if not self.current_scan:
            return []
        return [f for f in self.current_scan.files if getattr(f, 'clean_safety', 'confirm') == 'safe']

    def get_confirm_clean_list(self) -> List[FileItem]:
        """获取需手动确认的文件列表（clean_safety == 'confirm'）"""
        if not self.current_scan:
            return []
        return [f for f in self.current_scan.files if getattr(f, 'clean_safety', 'confirm') == 'confirm']

    def auto_clean_files(self) -> int:
        """自动清理所有可安全清理的文件，返回成功清理的数量"""
        if not self.current_scan:
            return 0
        count = 0
        for file in self.get_auto_clean_list():
            try:
                if os.path.isdir(file.path):
                    os.rmdir(file.path)
                else:
                    os.remove(file.path)
                logger.info(f"自动清理: {file.path}")
                count += 1
            except Exception as e:
                logger.warning(f"自动清理失败: {file.path} {e}")
        return count