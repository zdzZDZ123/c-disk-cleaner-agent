#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库接口 - 处理应用数据的持久化和检索
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union, Any
import sqlite3
from loguru import logger

from data.models import ScanResult, CleanTask, FileItem, BackupInfo, LogEntry, CleanCategory


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path=None):
        """初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，如果为None则使用默认路径
        """
        # 默认放在用户目录下
        if db_path is None:
            db_dir = Path.home() / ".c_disk_cleaner"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / "cleaner.db"
        
        self.db_path = db_path
        self.conn = None
        self.init_database()
    
    def init_database(self):
        """初始化数据库，创建表结构"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # 启用外键约束
            self.conn.execute("PRAGMA foreign_keys = ON")
            # 使用Row作为行工厂
            self.conn.row_factory = sqlite3.Row
            
            # 创建表
            with self.conn:
                # 扫描结果表
                self.conn.execute('''
                CREATE TABLE IF NOT EXISTS scan_results (
                    scan_id TEXT PRIMARY KEY,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    total_items INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    by_category TEXT,
                    scan_paths TEXT,
                    exclude_paths TEXT,
                    is_complete BOOLEAN DEFAULT 0,
                    duplicate_sets TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 文件项表
                self.conn.execute('''
                CREATE TABLE IF NOT EXISTS file_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    size INTEGER DEFAULT 0,
                    type TEXT,
                    category TEXT,
                    modified_time TIMESTAMP,
                    accessed_time TIMESTAMP,
                    created_time TIMESTAMP,
                    is_hidden BOOLEAN DEFAULT 0,
                    can_delete BOOLEAN DEFAULT 1,
                    attributes TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scan_results(scan_id) ON DELETE CASCADE
                )
                ''')
                
                # 清理任务表
                self.conn.execute('''
                CREATE TABLE IF NOT EXISTS clean_tasks (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    scan_id TEXT,
                    created_time TIMESTAMP NOT NULL,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    files_to_clean TEXT,
                    categories TEXT,
                    status TEXT DEFAULT 'pending',
                    progress REAL DEFAULT 0.0,
                    total_size INTEGER DEFAULT 0,
                    cleaned_size INTEGER DEFAULT 0,
                    error_message TEXT,
                    backup_id TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scan_results(scan_id) ON DELETE SET NULL
                )
                ''')
                
                # 备份信息表
                self.conn.execute('''
                CREATE TABLE IF NOT EXISTS backup_info (
                    backup_id TEXT PRIMARY KEY,
                    created_time TIMESTAMP NOT NULL,
                    task_id TEXT,
                    files TEXT,
                    backup_path TEXT NOT NULL,
                    total_size INTEGER DEFAULT 0,
                    is_valid BOOLEAN DEFAULT 1,
                    FOREIGN KEY (task_id) REFERENCES clean_tasks(task_id) ON DELETE SET NULL
                )
                ''')
                
                # 日志表
                self.conn.execute('''
                CREATE TABLE IF NOT EXISTS log_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT,
                    function TEXT,
                    task_id TEXT,
                    details TEXT,
                    FOREIGN KEY (task_id) REFERENCES clean_tasks(task_id) ON DELETE SET NULL
                )
                ''')
                
                # 创建索引
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_file_items_scan_id ON file_items(scan_id)')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_file_items_path ON file_items(path)')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_clean_tasks_scan_id ON clean_tasks(scan_id)')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_backup_info_task_id ON backup_info(task_id)')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_log_entries_task_id ON log_entries(task_id)')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_log_entries_timestamp ON log_entries(timestamp)')
                
            logger.info(f"数据库初始化完成: {self.db_path}")
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    # 扫描结果操作
    def save_scan_result(self, scan_result: ScanResult) -> bool:
        """保存扫描结果
        
        Args:
            scan_result: 扫描结果对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.conn:
                # 保存扫描结果
                self.conn.execute('''
                INSERT OR REPLACE INTO scan_results 
                (scan_id, start_time, end_time, total_items, total_size, 
                 by_category, scan_paths, exclude_paths, is_complete, duplicate_sets)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    scan_result.scan_id,
                    scan_result.start_time.isoformat(),
                    scan_result.end_time.isoformat() if scan_result.end_time else None,
                    scan_result.total_items,
                    scan_result.total_size,
                    json.dumps({k.value: v for k, v in scan_result.by_category.items()}),
                    json.dumps(scan_result.scan_paths),
                    json.dumps(scan_result.exclude_paths),
                    scan_result.is_complete,
                    json.dumps(scan_result.duplicate_sets)
                ))
                
                # 保存文件项
                if scan_result.files:
                    # 先删除旧的文件项
                    self.conn.execute("DELETE FROM file_items WHERE scan_id = ?", (scan_result.scan_id,))
                    
                    # 批量插入文件项
                    file_items_data = []
                    for file_item in scan_result.files:
                        file_items_data.append((
                            scan_result.scan_id,
                            file_item.path,
                            file_item.name,
                            file_item.size,
                            file_item.type,
                            file_item.category,
                            file_item.modified_time.isoformat(),
                            file_item.accessed_time.isoformat() if file_item.accessed_time else None,
                            file_item.created_time.isoformat() if file_item.created_time else None,
                            file_item.is_hidden,
                            file_item.can_delete,
                            json.dumps(file_item.attributes)
                        ))
                    
                    self.conn.executemany('''
                    INSERT INTO file_items
                    (scan_id, path, name, size, type, category, modified_time, 
                     accessed_time, created_time, is_hidden, can_delete, attributes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', file_items_data)
                
            return True
        except Exception as e:
            logger.error(f"保存扫描结果失败: {e}")
            return False
    
    def get_scan_result(self, scan_id: str) -> Optional[ScanResult]:
        """获取扫描结果
        
        Args:
            scan_id: 扫描ID
            
        Returns:
            扫描结果对象或None
        """
        try:
            cursor = self.conn.cursor()
            # 获取扫描结果
            cursor.execute("SELECT * FROM scan_results WHERE scan_id = ?", (scan_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # 获取文件项
            cursor.execute("SELECT * FROM file_items WHERE scan_id = ?", (scan_id,))
            file_items_rows = cursor.fetchall()
            
            # 构造文件项列表
            files = []
            for file_row in file_items_rows:
                file_item = FileItem(
                    path=file_row['path'],
                    name=file_row['name'],
                    size=file_row['size'],
                    type=file_row['type'],
                    category=CleanCategory(file_row['category']),
                    modified_time=datetime.fromisoformat(file_row['modified_time']),
                    accessed_time=datetime.fromisoformat(file_row['accessed_time']) if file_row['accessed_time'] else None,
                    created_time=datetime.fromisoformat(file_row['created_time']) if file_row['created_time'] else None,
                    is_hidden=bool(file_row['is_hidden']),
                    can_delete=bool(file_row['can_delete']),
                    attributes=json.loads(file_row['attributes'])
                )
                files.append(file_item)
            
            # 解析类别统计
            by_category = {}
            if row['by_category']:
                category_dict = json.loads(row['by_category'])
                for k, v in category_dict.items():
                    try:
                        by_category[CleanCategory(k)] = v
                    except ValueError:
                        logger.warning(f"Skipping unknown category '{k}' from database for scan {scan_id}")
            
            # 解析重复文件集
            duplicate_sets = []
            if row['duplicate_sets']:
                duplicate_sets = json.loads(row['duplicate_sets'])
            
            # 构造扫描结果
            scan_result = ScanResult(
                scan_id=row['scan_id'],
                start_time=datetime.fromisoformat(row['start_time']),
                end_time=datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
                total_items=row['total_items'],
                total_size=row['total_size'],
                by_category=by_category,
                scan_paths=json.loads(row['scan_paths']),
                exclude_paths=json.loads(row['exclude_paths']),
                is_complete=bool(row['is_complete']),
                files=files,
                duplicate_sets=duplicate_sets
            )
            
            return scan_result
        except Exception as e:
            logger.error(f"获取扫描结果失败: {e}")
            return None
    
    def list_scan_results(self, limit=10, offset=0) -> List[Dict]:
        """列出扫描结果
        
        Args:
            limit: 结果数量限制
            offset: 结果偏移量
            
        Returns:
            扫描结果摘要列表
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT scan_id, start_time, end_time, total_items, total_size, is_complete
            FROM scan_results
            ORDER BY start_time DESC
            LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'scan_id': row['scan_id'],
                    'start_time': datetime.fromisoformat(row['start_time']),
                    'end_time': datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
                    'total_items': row['total_items'],
                    'total_size': row['total_size'],
                    'is_complete': bool(row['is_complete'])
                })
            
            return results
        except Exception as e:
            logger.error(f"列出扫描结果失败: {e}")
            return []
    
    def delete_scan_result(self, scan_id: str) -> bool:
        """删除扫描结果
        
        Args:
            scan_id: 扫描ID
            
        Returns:
            是否删除成功
        """
        try:
            with self.conn:
                # 级联删除将自动删除关联的文件项
                self.conn.execute("DELETE FROM scan_results WHERE scan_id = ?", (scan_id,))
            return True
        except Exception as e:
            logger.error(f"删除扫描结果失败: {e}")
            return False
    
    # 清理任务操作
    def save_clean_task(self, task: CleanTask) -> bool:
        """保存清理任务
        
        Args:
            task: 清理任务对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.conn:
                self.conn.execute('''
                INSERT OR REPLACE INTO clean_tasks
                (task_id, name, scan_id, created_time, start_time, end_time, 
                 files_to_clean, categories, status, progress, total_size, 
                 cleaned_size, error_message, backup_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task.task_id,
                    task.name,
                    task.scan_id,
                    task.created_time.isoformat(),
                    task.start_time.isoformat() if task.start_time else None,
                    task.end_time.isoformat() if task.end_time else None,
                    json.dumps(task.files_to_clean),
                    json.dumps([str(c) for c in task.categories]),
                    task.status,
                    task.progress,
                    task.total_size,
                    task.cleaned_size,
                    task.error_message,
                    task.backup_id
                ))
            return True
        except Exception as e:
            logger.error(f"保存清理任务失败: {e}")
            return False
    
    def get_clean_task(self, task_id: str) -> Optional[CleanTask]:
        """获取清理任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            清理任务对象或None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM clean_tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # 解析类别列表
            categories = []
            if row['categories']:
                for c in json.loads(row['categories']):
                    categories.append(CleanCategory(c))
            
            # 构造任务对象
            task = CleanTask(
                task_id=row['task_id'],
                name=row['name'],
                scan_id=row['scan_id'],
                created_time=datetime.fromisoformat(row['created_time']),
                start_time=datetime.fromisoformat(row['start_time']) if row['start_time'] else None,
                end_time=datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
                files_to_clean=json.loads(row['files_to_clean']),
                categories=categories,
                status=row['status'],
                progress=row['progress'],
                total_size=row['total_size'],
                cleaned_size=row['cleaned_size'],
                error_message=row['error_message'],
                backup_id=row['backup_id']
            )
            
            return task
        except Exception as e:
            logger.error(f"获取清理任务失败: {e}")
            return None
    
    def list_clean_tasks(self, limit=10, offset=0) -> List[Dict]:
        """列出清理任务
        
        Args:
            limit: 结果数量限制
            offset: 结果偏移量
            
        Returns:
            清理任务摘要列表
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT task_id, name, scan_id, created_time, status, progress, total_size, cleaned_size
            FROM clean_tasks
            ORDER BY created_time DESC
            LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'task_id': row['task_id'],
                    'name': row['name'],
                    'scan_id': row['scan_id'],
                    'created_time': datetime.fromisoformat(row['created_time']),
                    'status': row['status'],
                    'progress': row['progress'],
                    'total_size': row['total_size'],
                    'cleaned_size': row['cleaned_size']
                })
            
            return results
        except Exception as e:
            logger.error(f"列出清理任务失败: {e}")
            return []
    
    def delete_clean_task(self, task_id: str) -> bool:
        """删除清理任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否删除成功
        """
        try:
            with self.conn:
                self.conn.execute("DELETE FROM clean_tasks WHERE task_id = ?", (task_id,))
            return True
        except Exception as e:
            logger.error(f"删除清理任务失败: {e}")
            return False
    
    # 备份信息操作
    def save_backup_info(self, backup: BackupInfo) -> bool:
        """保存备份信息
        
        Args:
            backup: 备份信息对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.conn:
                self.conn.execute('''
                INSERT OR REPLACE INTO backup_info
                (backup_id, created_time, task_id, files, backup_path, total_size, is_valid)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    backup.backup_id,
                    backup.created_time.isoformat(),
                    backup.task_id,
                    json.dumps(backup.files),
                    backup.backup_path,
                    backup.total_size,
                    backup.is_valid
                ))
            return True
        except Exception as e:
            logger.error(f"保存备份信息失败: {e}")
            return False
    
    def get_backup_info(self, backup_id: str) -> Optional[BackupInfo]:
        """获取备份信息
        
        Args:
            backup_id: 备份ID
            
        Returns:
            备份信息对象或None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM backup_info WHERE backup_id = ?", (backup_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # 构造备份信息对象
            backup = BackupInfo(
                backup_id=row['backup_id'],
                created_time=datetime.fromisoformat(row['created_time']),
                task_id=row['task_id'],
                files=json.loads(row['files']),
                backup_path=row['backup_path'],
                total_size=row['total_size'],
                is_valid=bool(row['is_valid'])
            )
            
            return backup
        except Exception as e:
            logger.error(f"获取备份信息失败: {e}")
            return None
    
    def list_backup_info(self, limit=10, offset=0) -> List[Dict]:
        """列出备份信息
        
        Args:
            limit: 结果数量限制
            offset: 结果偏移量
            
        Returns:
            备份信息摘要列表
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT backup_id, created_time, task_id, backup_path, total_size, is_valid
            FROM backup_info
            ORDER BY created_time DESC
            LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            results = []
            for row in cursor.fetchall():
                # 获取文件数量
                cursor.execute(
                    "SELECT files FROM backup_info WHERE backup_id = ?", 
                    (row['backup_id'],)
                )
                files_data = cursor.fetchone()
                file_count = 0
                if files_data and files_data['files']:
                    file_count = len(json.loads(files_data['files']))
                
                results.append({
                    'backup_id': row['backup_id'],
                    'created_time': datetime.fromisoformat(row['created_time']),
                    'task_id': row['task_id'],
                    'backup_path': row['backup_path'],
                    'total_size': row['total_size'],
                    'is_valid': bool(row['is_valid']),
                    'file_count': file_count
                })
            
            return results
        except Exception as e:
            logger.error(f"列出备份信息失败: {e}")
            return []
    
    def delete_backup_info(self, backup_id: str) -> bool:
        """删除备份信息
        
        Args:
            backup_id: 备份ID
            
        Returns:
            是否删除成功
        """
        try:
            with self.conn:
                self.conn.execute("DELETE FROM backup_info WHERE backup_id = ?", (backup_id,))
            return True
        except Exception as e:
            logger.error(f"删除备份信息失败: {e}")
            return False
    
    # 日志操作
    def save_log(self, log: LogEntry) -> bool:
        """保存日志
        
        Args:
            log: 日志条目对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT INTO log_entries
                (timestamp, level, message, module, function, task_id, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    log.timestamp.isoformat(),
                    log.level,
                    log.message,
                    log.module,
                    log.function,
                    log.task_id,
                    json.dumps(log.details)
                ))
                log.id = cursor.lastrowid
            return True
        except Exception as e:
            logger.error(f"保存日志失败: {e}")
            return False
    
    def get_logs(self, task_id=None, level=None, limit=100, offset=0) -> List[LogEntry]:
        """获取日志
        
        Args:
            task_id: 任务ID过滤
            level: 日志级别过滤
            limit: 结果数量限制
            offset: 结果偏移量
            
        Returns:
            日志条目列表
        """
        try:
            cursor = self.conn.cursor()
            
            # 构建查询
            query = "SELECT * FROM log_entries"
            params = []
            
            # 添加过滤条件
            conditions = []
            if task_id:
                conditions.append("task_id = ?")
                params.append(task_id)
            if level:
                conditions.append("level = ?")
                params.append(level)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            # 添加排序和分页
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            # 执行查询
            cursor.execute(query, params)
            
            logs = []
            for row in cursor.fetchall():
                log = LogEntry(
                    id=row['id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    level=row['level'],
                    message=row['message'],
                    module=row['module'],
                    function=row['function'],
                    task_id=row['task_id'],
                    details=json.loads(row['details']) if row['details'] else {}
                )
                logs.append(log)
            
            return logs
        except Exception as e:
            logger.error(f"获取日志失败: {e}")
            return []
    
    def clear_logs(self, days=30) -> int:
        """清理旧日志
        
        Args:
            days: 保留天数
            
        Returns:
            清理的日志数量
        """
        try:
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM log_entries WHERE timestamp < ?", (cutoff_date,))
                return cursor.rowcount
        except Exception as e:
            logger.error(f"清理日志失败: {e}")
            return 0