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
from typing import List, Dict, Set, Tuple, Generator, Optional
import threading
import queue
import psutil
from loguru import logger

from data.models import FileItem, ScanResult, FileType, CleanCategory
from config.manager import ConfigManager


class Scanner:
    """文件扫描器类，负责扫描C盘文件"""
    
    def __init__(self, config_manager=None):
        """初始化扫描器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
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
            scan_paths = self.config.get('scanner.include_dirs', ["C:\\Users"])
        
        if exclude_paths is None:
            exclude_paths = self.config.get('scanner.exclude_dirs', 
                                         ["C:\\Windows", 
                                          "C:\\Program Files", 
                                          "C:\\Program Files (x86)"])
        
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
                return
            
            try:
                # 列出目录内容
                for entry in os.scandir(current_path):
                    if self._stop_event.is_set():
                        break
                    
                    # 如果暂停，等待恢复
                    while self._pause_event.is_set() and not self._stop_event.is_set():
                        time.sleep(0.5)
                    
                    try:
                        # 如果是排除的路径，则跳过
                        if _is_excluded(entry.path):
                            continue
                        
                        # 获取文件信息
                        try:
                            stat_info = entry.stat(follow_symlinks=follow_links)
                        except (PermissionError, OSError):
                            continue  # 无法访问的文件，跳过
                        
                        # 生成文件信息
                        yield entry.path, stat_info
                        
                        # 如果是目录，并且允许递归，则继续遍历
                        if entry.is_dir(follow_symlinks=follow_links) and recursive:
                            yield from _walk_impl(entry.path, current_depth + 1)
                            
                    except (PermissionError, OSError) as e:
                        logger.debug(f"无法访问 {entry.path}: {e}")
                        continue
                    
            except (PermissionError, OSError) as e:
                logger.debug(f"无法访问目录 {current_path}: {e}")
        
        # 开始遍历
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
                if suffix in {'.tmp', '.temp', '.bak', '~'}:
                    file_type = FileType.TEMP
                elif suffix in {'.log', '.log.1', '.log.old'}:
                    file_type = FileType.LOG
                elif suffix in {'.cache', '.cach'}:
                    file_type = FileType.CACHE
                
            # 判断清理类别
            category = self._categorize_file(file_path, path_obj, file_type)
            
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
                attributes={}
            )
            
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
            ["*.tmp", "*.temp", "~*", "*.bak"]
        )
        if any(self._match_pattern(path_obj.name, p) for p in temp_patterns):
            return CleanCategory.TEMP_FILES
        
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
        windows_cache_paths = self.config.get(
            "rules.windows_cache.paths", 
            ["C:\\Windows\\Temp", "%TEMP%", 
             "%SYSTEMROOT%\\SoftwareDistribution\\Download"]
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
                if datetime.now() - mod_time > timedelta(days=days_old):
                    return CleanCategory.OLD_FILES
            except OSError as e:
                 logger.debug(f"無法獲取文件時間 {file_path}: {e}")
            
        # 回收站
        if file_path.lower().startswith("c:\\$recycle.bin"):
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
        # 系统保护的路径不应该删除
        system_paths = [
            "C:\\Windows",
            "C:\\Program Files",
            "C:\\Program Files (x86)",
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
        
        # TODO: 添加更多的安全检查
        
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