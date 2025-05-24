#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
日志服务 - 处理应用日志的收集、记录和查询
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from loguru import logger
import logging

# from data.models import LogEntry # Commented out for testing
from data.database import Database
from config.manager import ConfigManager


class DatabaseHandler:
    """数据库日志处理器，将日志存储到数据库"""
    
    def __init__(self, database=None):
        """初始化数据库日志处理器
        
        Args:
            database: 数据库实例，如果为None则创建新实例
        """
        self.db = database or Database()
    
    def write(self, message):
        """写入日志到数据库
        
        Args:
            message: 日志消息字典
        """
        try:
            # 构造日志条目
            record = message.record
            
            # --- 由于 LogEntry 被注释，这里暂时无法创建对象 --- #
            # log_entry = LogEntry(
            #     id=0,  # 数据库会自动分配ID
            #     timestamp=record["time"].datetime,
            #     level=record["level"].name,
            #     message=record["message"],
            #     module=record["name"],
            #     function=record["function"],
            #     task_id=record.get("extra", {}).get("task_id"),
            #     details={
            #         "line": record["line"],
            #         "file": record["file"].path,
            #         "process": record["process"].id,
            #         "thread": record["thread"].id,
            #         "exception": str(record["exception"]) if record["exception"] else None,
            #         "elapsed": record["elapsed"].total_seconds()
            #     }
            # )
            # --- ----------------------------------------- --- #
            
            # 保存到数据库 (需要调整，因为 LogEntry 不可用)
            # 暂时直接传递 record 字典的关键信息，或者跳过保存
            # self.db.save_log(log_entry) # 必须注释掉或修改
            print(f"[DB Handler - LogEntry commented out]: {record['message']}", file=sys.stderr)
            
        except Exception as e:
            # 这里不能用logger记录，否则可能导致递归调用
            print(f"Failed to save log to database: {e}", file=sys.stderr)
    
    def close(self):
        """关闭处理器，释放资源"""
        self.db.close()


class LoggerService:
    """日志服务类，处理日志的收集、记录和查询"""
    
    def __init__(self, config_manager=None, database=None):
        """初始化日志服务
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
            database: 数据库实例，如果为None则创建新实例
        """
        self.config = config_manager or ConfigManager()
        self.db = database or Database()
        self.db_handler = None
        self.setup_logger()
    
    def setup_logger(self):
        """设置日志服务"""
        # 创建日志目录
        log_dir = Path.home() / ".c_disk_cleaner" / "logs"
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # 移除所有日志处理器
        logger.remove()
        
        # 获取日志级别
        log_level = self.config.get('logging.level', 'INFO')
        
        # 添加控制台处理器
        if self.config.get('logging.console.enabled', True):
            logger.add(
                sys.stderr,
                level=log_level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
            )
        
        # 添加文件处理器
        if self.config.get('logging.file.enabled', True):
            log_file = log_dir / "app_{time}.log"
            logger.add(
                str(log_file),
                rotation=self.config.get('logging.file.rotation', '10 MB'),
                retention=self.config.get('logging.file.retention', '1 week'),
                level=log_level,
                encoding='utf-8'
            )
        
        # 添加数据库处理器
        if self.config.get('logging.database.enabled', False):
            self.db_handler = DatabaseHandler(self.db)
            logger.add(
                self.db_handler.write,
                level=log_level
            )
    
    def get_logger(self, name=None):
        """获取日志记录器
        Args:
            name: 日志记录器名称，可选
        Returns:
            logger: 日志记录器实例
        """
        return logger
    
    def close(self):
        """关闭日志服务，释放资源"""
        if self.db_handler:
            self.db_handler.close()


# 简单测试
if __name__ == "__main__":
    # 创建日志服务
    log_service = LoggerService()
    log = log_service.get_logger()
    
    # 测试日志
    log.debug("这是一条调试日志")
    log.info("这是一条信息日志")
    log.warning("这是一条警告日志")
    log.error("这是一条错误日志")
    log.critical("这是一条严重错误日志")
    
    # 测试带上下文的日志
    task_logger = log.bind(task_id="test-task-001")
    task_logger.info("这是一条带任务ID的日志")
    
    # 关闭日志服务
    log_service.close()