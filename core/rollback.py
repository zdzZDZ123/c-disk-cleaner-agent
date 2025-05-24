#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
回滚模块 - 负责从备份还原误删的文件
"""

import os
import shutil
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger

from data.models import BackupInfo
from config.manager import ConfigManager


class Rollback:
    """回滚管理器，负责文件还原操作"""
    
    def __init__(self, config_manager=None):
        """初始化回滚管理器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
        """
        self.config = config_manager or ConfigManager()
        
        # 备份目录路径
        backup_dir = self.config.get('safety.backup.path', None)
        if not backup_dir:
            backup_dir = Path.home() / ".c_disk_cleaner" / "backups"
        self.backup_dir = Path(backup_dir)
    
    def list_backups(self) -> List[Dict]:
        """列出所有可用的备份
        
        Returns:
            备份信息列表，按创建时间降序排序
        """
        backups = []
        
        try:
            # 确保备份目录存在
            if not self.backup_dir.exists():
                return []
            
            # 遍历备份目录中的所有备份信息文件
            for info_file in self.backup_dir.glob("*.json"):
                try:
                    # 加载备份信息
                    with open(info_file, "r", encoding="utf-8") as f:
                        backup_data = json.load(f)
                    
                    # 检查备份是否有效
                    backup_id = backup_data.get("backup_id")
                    backup_path = self.backup_dir / backup_id
                    is_valid = backup_path.exists() and backup_data.get("is_valid", False)
                    
                    # 构造备份摘要信息
                    backup_info = {
                        "backup_id": backup_id,
                        "created_time": datetime.fromisoformat(backup_data.get("created_time")),
                        "task_id": backup_data.get("task_id"),
                        "total_size": backup_data.get("total_size", 0),
                        "file_count": len(backup_data.get("files", [])),
                        "is_valid": is_valid
                    }
                    
                    backups.append(backup_info)
                except Exception as e:
                    logger.warning(f"加载备份信息失败 {info_file}: {e}")
                    continue
            
            # 按创建时间降序排序
            backups.sort(key=lambda x: x["created_time"], reverse=True)
            
        except Exception as e:
            logger.error(f"列出备份失败: {e}")
        
        return backups
    
    def get_backup_info(self, backup_id: str) -> Optional[BackupInfo]:
        """获取指定备份的详细信息
        
        Args:
            backup_id: 备份ID
            
        Returns:
            备份信息对象或None（如果备份不存在）
        """
        try:
            # 备份信息文件路径
            backup_info_path = self.backup_dir / f"{backup_id}.json"
            if not backup_info_path.exists():
                logger.warning(f"备份信息不存在: {backup_id}")
                return None
            
            # 加载备份信息
            with open(backup_info_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
            
            # 构造备份信息对象
            backup_info = BackupInfo(**backup_data)
            
            # 检查备份是否有效
            backup_path = self.backup_dir / backup_id
            backup_info.is_valid = backup_path.exists() and backup_info.is_valid
            
            return backup_info
            
        except Exception as e:
            logger.error(f"获取备份信息失败: {e}")
            return None
    
    def restore_backup(self, backup_id: str, selected_files: List[str] = None) -> bool:
        """从备份还原文件
        
        Args:
            backup_id: 备份ID
            selected_files: 要还原的文件路径列表，如果为None则还原所有文件
            
        Returns:
            是否成功还原
        """
        try:
            # 获取备份信息
            backup_info = self.get_backup_info(backup_id)
            if not backup_info:
                return False
            
            if not backup_info.is_valid:
                logger.error(f"备份已失效: {backup_id}")
                return False
            
            # 备份文件目录
            backup_files_dir = self.backup_dir / backup_id
            if not backup_files_dir.exists():
                logger.error(f"备份文件不存在: {backup_id}")
                return False
            
            # 开始还原
            logger.info(f"开始从备份 {backup_id} 还原文件")
            restored_count = 0
            failed_count = 0
            
            # 筛选要还原的文件
            files_to_restore = backup_info.files
            if selected_files:
                files_to_restore = [
                    f for f in backup_info.files 
                    if f.get("original_path") in selected_files
                ]
            
            # 还原文件
            for file_info in files_to_restore:
                src_path = backup_files_dir / file_info.get("rel_path")
                dst_path = Path(file_info.get("original_path"))
                
                try:
                    # 确保目标目录存在
                    dst_path.parent.mkdir(exist_ok=True, parents=True)
                    
                    # 复制文件或目录
                    if file_info.get("is_dir", False):
                        if dst_path.exists():
                            shutil.rmtree(dst_path)
                        shutil.copytree(src_path, dst_path)
                    else:
                        if dst_path.exists():
                            os.remove(dst_path)
                        shutil.copy2(src_path, dst_path)
                    
                    restored_count += 1
                    logger.debug(f"还原文件成功: {dst_path}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"还原文件失败 {dst_path}: {e}")
            
            logger.info(f"备份还原完成: 成功还原 {restored_count} 个文件, 失败 {failed_count} 个文件")
            return restored_count > 0
            
        except Exception as e:
            logger.exception(f"还原备份失败: {e}")
            return False
    
    def delete_backup(self, backup_id: str) -> bool:
        """删除备份
        
        Args:
            backup_id: 备份ID
            
        Returns:
            是否成功删除
        """
        try:
            # 备份信息文件路径
            backup_info_path = self.backup_dir / f"{backup_id}.json"
            if not backup_info_path.exists():
                logger.warning(f"备份信息不存在: {backup_id}")
                return False
            
            # 备份文件目录
            backup_files_dir = self.backup_dir / backup_id
            
            # 删除备份文件目录
            if backup_files_dir.exists():
                if backup_files_dir.is_dir():
                    shutil.rmtree(backup_files_dir)
                else:
                    backup_files_dir.unlink()
            
            # 删除备份信息文件
            backup_info_path.unlink()
            
            logger.info(f"备份已删除: {backup_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除备份失败: {e}")
            return False
    
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
            from datetime import timedelta
            
            # 计算截止日期
            cutoff_date = datetime.now() - timedelta(days=days)
            cleaned_count = 0
            
            # 获取所有备份
            backups = self.list_backups()
            
            # 筛选要删除的备份
            for backup in backups:
                if backup["created_time"] < cutoff_date:
                    # 删除备份
                    if self.delete_backup(backup["backup_id"]):
                        cleaned_count += 1
            
            logger.info(f"清理旧备份完成，共删除了 {cleaned_count} 个备份")
            return cleaned_count
            
        except Exception as e:
            logger.exception(f"清理旧备份失败: {e}")
            return 0