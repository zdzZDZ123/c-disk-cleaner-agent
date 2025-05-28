#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
清理模块 - 负责安全删除文件
"""

import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
import threading
from loguru import logger

from data.models import FileItem, CleanTask, BackupInfo, CleanCategory
from config.manager import ConfigManager


class Cleaner:
    """文件清理器，负责安全删除文件"""
    
    def __init__(self, config_manager=None):
        """初始化清理器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
        """
        self.config = config_manager or ConfigManager()
        self.current_task: Optional[CleanTask] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._is_cleaning = False
        self._clean_thread = None
        
        # 备份目录路径
        backup_dir = self.config.get('safety.backup.path', None)
        if not backup_dir:
            backup_dir = Path.home() / ".c_disk_cleaner" / "backups"
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True, parents=True)
        
    def start_clean_task(self, files_to_clean: List[FileItem], 
                      categories: List[CleanCategory] = None, 
                      task_name: str = None,
                      create_backup: bool = None) -> str:
        """启动新的清理任务
        
        Args:
            files_to_clean: 要清理的文件项列表
            categories: 要清理的类别列表，如果不为None，则只清理这些类别的文件
            task_name: 任务名称，如果为None则自动生成
            create_backup: 是否创建备份，如果为None则使用配置值
            
        Returns:
            清理任务ID，如果失败则返回空字符串
        """
        if self._is_cleaning:
            logger.warning("已有清理任务正在运行，请先停止当前任务")
            return ""
        
        # 重置事件
        self._stop_event.clear()
        self._pause_event.clear()
        
        # 处理备份选项
        if create_backup is None:
            create_backup = self.config.get('safety.backup.enabled', True)
        
        # 过滤文件列表（如果指定了类别）
        filtered_files = files_to_clean
        if categories:
            filtered_files = [file for file in files_to_clean 
                             if file.category in categories]
        
        if not filtered_files:
            logger.warning("没有符合条件的文件需要清理")
            return ""
        
        # 计算总大小
        total_size = sum(file.size for file in filtered_files)
        
        # 创建任务
        task_id = str(uuid.uuid4())
        if not task_name:
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_name = f"清理任务_{now}"
            
        self.current_task = CleanTask(
            task_id=task_id,
            name=task_name,
            created_time=datetime.now(),
            files_to_clean=[file.path for file in filtered_files],
            categories=categories if categories else [],
            status="pending",
            progress=0.0,
            total_size=total_size,
            cleaned_size=0,
        )
        
        # 如果需要备份，先创建备份
        if create_backup:
            backup_id = self._create_backup(filtered_files)
            if backup_id:
                self.current_task.backup_id = backup_id
            else:
                logger.warning("创建备份失败，但清理任务将继续")
        
        # 启动清理线程
        self._is_cleaning = True
        self._clean_thread = threading.Thread(
            target=self._clean_worker, 
            args=(filtered_files,)
        )
        self._clean_thread.daemon = True
        self.current_task.status = "running"
        self.current_task.start_time = datetime.now()
        self._clean_thread.start()
        
        logger.info(f"开始新清理任务 {task_id}, 共 {len(filtered_files)} 个文件, 总大小: {total_size / (1024*1024):.2f} MB")
        # 清理完成后统计空间
        cleaned_size = sum(f.size for f in files_to_clean)
        logger.info(f"本次清理释放空间：{cleaned_size / (1024*1024):.2f} MB")
        print(f"本次清理释放空间：{cleaned_size / (1024*1024):.2f} MB")
        return task_id
    
    def stop_clean_task(self) -> bool:
        """停止当前清理任务
        
        Returns:
            是否成功停止
        """
        if not self._is_cleaning:
            return False
        
        logger.info("正在停止清理任务...")
        self._stop_event.set()
        
        # 等待线程结束
        if self._clean_thread and self._clean_thread.is_alive():
            self._clean_thread.join(timeout=5.0)
        
        # 更新任务状态
        if self.current_task:
            self.current_task.end_time = datetime.now()
            self.current_task.status = "stopped"
        
        self._is_cleaning = False
        logger.info("清理任务已停止")
        return True
    
    def pause_clean_task(self) -> bool:
        """暂停当前清理任务
        
        Returns:
            是否成功暂停
        """
        if not self._is_cleaning:
            return False
        
        self._pause_event.set()
        if self.current_task:
            self.current_task.status = "paused"
        logger.info("清理任务已暂停")
        return True
    
    def resume_clean_task(self) -> bool:
        """恢复当前清理任务
        
        Returns:
            是否成功恢复
        """
        if not self._is_cleaning:
            return False
        
        self._pause_event.clear()
        if self.current_task:
            self.current_task.status = "running"
        logger.info("清理任务已恢复")
        return True
    
    def get_progress(self) -> Tuple[int, int, float]:
        """获取当前清理进度
        
        Returns:
            (已清理大小(字节), 总大小(字节), 完成百分比)
        """
        if not self.current_task:
            return 0, 0, 0.0
        
        cleaned_size = self.current_task.cleaned_size
        total_size = self.current_task.total_size
        
        if total_size > 0:
            progress = min(1.0, cleaned_size / total_size)
        else:
            progress = 0.0
            
        return cleaned_size, total_size, progress
    
    def is_cleaning(self) -> bool:
        """检查清理器是否正在清理"""
        return self._is_cleaning

    def get_current_task(self) -> Optional[CleanTask]:
        """获取当前清理任务
        
        Returns:
            当前清理任务或None
        """
        return self.current_task
    
    def restore_from_backup(self, backup_id: str) -> bool:
        """从备份还原文件
        
        Args:
            backup_id: 备份ID
            
        Returns:
            是否成功还原
        """
        # 如果正在清理，不允许还原
        if self._is_cleaning:
            logger.warning("有清理任务正在运行，无法还原备份")
            return False
        
        # 查找备份信息
        backup_info_path = self.backup_dir / f"{backup_id}.json"
        if not backup_info_path.exists():
            logger.error(f"备份信息不存在: {backup_id}")
            return False
        
        # 加载备份信息
        try:
            import json
            with open(backup_info_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
            
            backup_info = BackupInfo(**backup_data)
            if not backup_info.is_valid:
                logger.error(f"备份已失效: {backup_id}")
                return False
                
            # 备份存储路径
            backup_files_dir = self.backup_dir / backup_id
            if not backup_files_dir.exists():
                logger.error(f"备份文件不存在: {backup_id}")
                return False
            
            # 开始还原
            logger.info(f"开始从备份 {backup_id} 还原文件")
            restored = 0
            failed = 0
            
            for file_info in backup_info.files:
                src_path = backup_files_dir / file_info["rel_path"]
                dst_path = Path(file_info["original_path"])
                
                try:
                    # 确保目标目录存在
                    dst_path.parent.mkdir(exist_ok=True, parents=True)
                    
                    # 复制文件
                    if src_path.is_dir():
                        if not dst_path.exists():
                            shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
                        
                    restored += 1
                except Exception as e:
                    logger.error(f"还原文件失败 {file_info['original_path']}: {e}")
                    failed += 1
            
            logger.info(f"备份还原完成: 成功还原 {restored} 个文件, 失败 {failed} 个文件")
            return True
            
        except Exception as e:
            logger.exception(f"还原备份失败: {e}")
            return False
    
    def _clean_worker(self, files: List[FileItem]):
        """清理工作线程
        
        Args:
            files: 要清理的文件项列表
        """
        try:
            cleaned_count = 0
            cleaned_size = 0
            failed_count = 0
            
            # 更新任务开始状态
            if self.current_task:
                self.current_task.status = "running"
            
            # 遍历文件进行清理
            total_files = len(files)
            for i, file_item in enumerate(files):
                # 检查是否应该停止
                if self._stop_event.is_set():
                    break
                
                # 如果暂停，等待恢复
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.5)
                
                # 更新进度
                if self.current_task:
                    self.current_task.progress = i / total_files if total_files > 0 else 1.0
                
                # 删除文件
                success = self._safe_delete(file_item.path)
                
                # 更新计数
                if success:
                    cleaned_count += 1
                    cleaned_size += file_item.size
                    
                    # 更新任务状态
                    if self.current_task:
                        self.current_task.cleaned_size = cleaned_size
                else:
                    failed_count += 1
            
            # 更新任务完成状态
            if self.current_task and not self._stop_event.is_set():
                self.current_task.end_time = datetime.now()
                self.current_task.status = "completed"
                self.current_task.progress = 1.0
                
            logger.info(f"清理完成: 成功删除 {cleaned_count} 个文件, "
                      f"总大小: {cleaned_size / (1024*1024):.2f} MB, "
                      f"失败: {failed_count} 个文件")
                
        except Exception as e:
            logger.exception(f"清理过程出错: {e}")
            
            # 更新任务错误状态
            if self.current_task:
                self.current_task.status = "failed"
                self.current_task.error_message = str(e)
                self.current_task.end_time = datetime.now()
                
        finally:
            self._is_cleaning = False
    
    def _safe_delete(self, path: str) -> bool:
        """安全删除文件或目录，先移动到回收站目录
        Args:
            path: 文件或目录路径
        Returns:
            是否成功移动到回收站
        """
        try:
            path_obj = Path(path)
            # 如果路径不存在，视为成功
            if not path_obj.exists():
                return True
            # 回收站目录
            recycle_bin = Path.home() / ".c_disk_cleaner" / "recycle_bin"
            recycle_bin.mkdir(exist_ok=True, parents=True)
            # 生成唯一目标路径，保留原始相对路径
            rel_path = path_obj.relative_to(path_obj.anchor)
            target_path = recycle_bin / rel_path
            target_path.parent.mkdir(exist_ok=True, parents=True)
            # 如果目标已存在，重命名加时间戳
            if target_path.exists():
                import time
                target_path = target_path.with_name(f"{target_path.name}_{int(time.time())}")
            # 移动文件或目录
            shutil.move(str(path_obj), str(target_path))
            logger.info(f"已移动到回收站: {path} -> {target_path}")
            # 记录回收信息（可扩展为json日志）
            recycle_log = recycle_bin / "recycle_log.json"
            import json
            log_entry = {"original_path": str(path_obj), "recycle_path": str(target_path), "time": datetime.now().isoformat()}
            if recycle_log.exists():
                with open(recycle_log, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
            else:
                log_data = []
            log_data.append(log_entry)
            with open(recycle_log, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            return True
        except PermissionError:
            logger.warning(f"权限不足，无法移动到回收站: {path}")
            return False
        except FileNotFoundError:
            return True
        except Exception as e:
            logger.error(f"移动到回收站失败 {path}: {e}")
            return False
    
    def _create_backup(self, files: List[FileItem]) -> Optional[str]:
        """创建文件备份
        
        Args:
            files: 要备份的文件项列表
            
        Returns:
            备份ID或None（如果备份失败）
        """
        try:
            # 创建备份ID和目录
            backup_id = str(uuid.uuid4())
            backup_path = self.backup_dir / backup_id
            backup_path.mkdir(exist_ok=True)
            
            # 初始化备份信息
            backup_info = BackupInfo(
                backup_id=backup_id,
                created_time=datetime.now(),
                task_id=self.current_task.task_id if self.current_task else None,
                backup_path=str(backup_path),
                total_size=0,
                is_valid=True,
                files=[]
            )
            
            # 备份文件
            for file_item in files:
                original_path = Path(file_item.path)
                if not original_path.exists():
                    continue
                
                # 计算相对路径，用于存储
                rel_path = original_path.name
                if original_path.is_dir():
                    rel_path += "_dir"
                    
                # 目标备份路径
                target_path = backup_path / rel_path
                
                try:
                    # 复制文件或目录
                    if original_path.is_dir():
                        shutil.copytree(original_path, target_path)
                    else:
                        # 确保父目录存在
                        target_path.parent.mkdir(exist_ok=True, parents=True)
                        shutil.copy2(original_path, target_path)
                    
                    # 添加备份文件信息
                    backup_info.files.append({
                        "original_path": file_item.path,
                        "rel_path": rel_path,
                        "size": file_item.size,
                        "is_dir": original_path.is_dir()
                    })
                    backup_info.total_size += file_item.size
                    
                except Exception as e:
                    logger.warning(f"备份文件失败 {file_item.path}: {e}")
            
            # 保存备份信息
            import json
            backup_info_path = self.backup_dir / f"{backup_id}.json"
            with open(backup_info_path, "w", encoding="utf-8") as f:
                json.dump(backup_info.dict(), f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"创建备份成功: {backup_id}, "
                      f"包含 {len(backup_info.files)} 个文件, "
                      f"总大小: {backup_info.total_size / (1024*1024):.2f} MB")
            
            return backup_id
            
        except Exception as e:
            logger.exception(f"创建备份失败: {e}")
            return None
    
    def clean_old_backups(self, days: int = None) -> int:
        """清理旧备份
        
        Args:
            days: 保留天数，如果为None则使用配置值
        
        Returns:
            清理的备份数量
        """
        if days is None:
            days = self.config.get('safety.backup.retention_days', 30)
            
        if days <= 0:
            return 0
        
        try:
            import json
            from datetime import timedelta
            
            # 计算截止日期
            cutoff_date = datetime.now() - timedelta(days=days)
            cleaned_count = 0
            
            # 遍历备份目录
            for info_file in self.backup_dir.glob("*.json"):
                try:
                    # 读取备份信息
                    with open(info_file, "r", encoding="utf-8") as f:
                        backup_data = json.load(f)
                    
                    # 解析创建时间
                    created_time = datetime.fromisoformat(backup_data.get("created_time"))
                    backup_id = backup_data.get("backup_id")
                    
                    # 检查是否超过保留期
                    if created_time < cutoff_date:
                        # 删除备份文件
                        backup_path = self.backup_dir / backup_id
                        if backup_path.exists():
                            if backup_path.is_dir():
                                shutil.rmtree(backup_path)
                            else:
                                backup_path.unlink()
                        
                        # 删除信息文件
                        info_file.unlink()
                        
                        cleaned_count += 1
                        logger.debug(f"已删除旧备份: {backup_id}, 创建于 {created_time}")
                        
                except Exception as e:
                    logger.warning(f"处理备份文件失败 {info_file}: {e}")
                    continue
            
            logger.info(f"清理旧备份完成，共删除了 {cleaned_count} 个备份")
            return cleaned_count
            
        except Exception as e:
            logger.exception(f"清理旧备份失败: {e}")
            return 0
