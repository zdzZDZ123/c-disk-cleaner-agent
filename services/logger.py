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
    
    def __init__(self, log_file: str = "logs/app.log"):
        """初始化日志服务
        
        Args:
            log_file: 日志文件路径
        """
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        logger.remove()
        logger.add(sys.stdout, level="INFO", colorize=True, enqueue=True)
        logger.add(log_file, rotation="10 MB", retention="10 days", encoding="utf-8", enqueue=True)
        self.logger = logger
    
    def info(self, msg: str):
        """记录信息日志
        
        Args:
            msg: 日志消息
        """
        self.logger.info(msg)

    def warning(self, msg: str):
        """记录警告日志
        
        Args:
            msg: 日志消息
        """
        self.logger.warning(msg)

    def error(self, msg: str):
        """记录错误日志
        
        Args:
            msg: 日志消息
        """
        self.logger.error(msg)

    def debug(self, msg: str):
        """记录调试日志
        
        Args:
            msg: 日志消息
        """
        self.logger.debug(msg)


# 简单测试
if __name__ == "__main__":
    # 创建日志服务
    log_service = LoggerService()
    
    # 测试日志
    log_service.info("这是一条信息日志")
    log_service.warning("这是一条警告日志")
    log_service.error("这是一条错误日志")
    log_service.debug("这是一条调试日志")