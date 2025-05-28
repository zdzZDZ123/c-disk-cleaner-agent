#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据模型 - 定义应用使用的数据实体
"""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field
from dataclasses import dataclass


class FileType(str, Enum):
    """文件类型枚举"""
    REGULAR = "regular"        # 普通文件
    DIRECTORY = "directory"    # 目录
    SYMLINK = "symlink"        # 符号链接
    TEMP = "temp"              # 临时文件
    CACHE = "cache"            # 缓存文件
    LOG = "log"                # 日志文件
    BACKUP = "backup"          # 备份文件
    DOWNLOAD = "download"      # 下载文件
    DOCUMENT = "document"      # 文档文件
    MEDIA = "media"            # 媒体文件
    SYSTEM = "system"          # 系统文件
    UNKNOWN = "unknown"        # 未知类型


class CleanCategory(str, Enum):
    """清理类别枚举"""
    TEMP_FILES = "temp_files"           # 临时文件
    BROWSER_CACHE = "browser_cache"     # 浏览器缓存
    WINDOWS_CACHE = "windows_cache"     # Windows缓存
    LARGE_FILES = "large_files"         # 大文件
    OLD_FILES = "old_files"             # 旧文件
    DUPLICATE_FILES = "duplicate_files" # 重复文件
    RECYCLE_BIN = "recycle_bin"         # 回收站
    LOG_FILES = "log_files"             # 日志文件
    SYSTEM_CACHE = "system_cache"       # 系统缓存
    DOWNLOAD_TEMP = "download_temp"     # 下载临时文件
    DEVELOPMENT_CACHE = "development_cache" # 开发工具缓存
    OTHER = "other"                     # 其他


@dataclass
class FileItem:
    path: str
    size: int = 0
    mtime: float = 0.0
    hash: Optional[str] = None


@dataclass
class ScanResult:
    garbage_dirs: List[str]
    large_files: List[FileItem]
    duplicate_images: List[str]
    blurry_images: List[str]


@dataclass
class CleanTask:
    task_id: str
    items: List[FileItem]
    status: str = "pending"


@dataclass
class BackupInfo:
    backup_path: str
    original_path: str
    time: float


@dataclass
class LogEntry:
    time: float
    level: str
    message: str



class FileItem(BaseModel):
    """文件项模型"""
    path: str                                     # 文件路径
    name: str                                     # 文件名
    size: int                                     # 文件大小(字节)
    type: FileType = FileType.UNKNOWN            # 文件类型
    category: CleanCategory = CleanCategory.OTHER # 清理类别
    modified_time: datetime                       # 修改时间
    accessed_time: Optional[datetime] = None      # 访问时间
    created_time: Optional[datetime] = None       # 创建时间
    is_hidden: bool = False                       # 是否隐藏
    can_delete: bool = True                       # 是否可删除
    attributes: Dict = Field(default_factory=dict)# 文件属性
    clean_safety: str = "confirm"                 # 清理安全性: safe/confirm/forbid
    content_hash: Optional[str] = None            # 文件内容hash（如图片感知hash、视频hash等）
    content_summary: Optional[str] = None         # 文件内容摘要/描述
    access_count: Optional[int] = None            # 访问次数
    
    class Config:
        arbitrary_types_allowed = True


class ScanResult(BaseModel):
    """扫描结果模型"""
    scan_id: str                                  # 扫描ID
    start_time: datetime                          # 扫描开始时间
    end_time: Optional[datetime] = None           # 扫描结束时间
    total_items: int = 0                          # 扫描的总项目数
    total_size: int = 0                           # 总大小(字节)
    by_category: Dict[CleanCategory, int] = Field(default_factory=dict) # 按类别统计大小
    files: List[FileItem] = Field(default_factory=list)                 # 文件项列表
    scan_paths: List[str] = Field(default_factory=list)                 # 扫描路径
    exclude_paths: List[str] = Field(default_factory=list)              # 排除路径
    is_complete: bool = False                                          # 扫描是否完成
    duplicate_sets: List[List[str]] = Field(default_factory=list)      # 重复文件集 (路径列表)
    duplicate_images: List[List[str]] = Field(default_factory=list)    # 重复图片集 (路径列表)
    blurry_images: List[str] = Field(default_factory=list)             # 模糊图片路径列表
    
    class Config:
        arbitrary_types_allowed = True


class CleanTask(BaseModel):
    """清理任务模型"""
    task_id: str                                  # 任务ID
    name: str                                     # 任务名称
    scan_id: Optional[str] = None                 # 关联的扫描ID
    created_time: datetime                        # 创建时间
    start_time: Optional[datetime] = None         # 开始时间
    end_time: Optional[datetime] = None           # 结束时间
    files_to_clean: List[str] = Field(default_factory=list)       # 要清理的文件
    categories: List[CleanCategory] = Field(default_factory=list) # 清理类别
    status: str = "pending"                       # 任务状态(pending/running/completed/failed)
    progress: float = 0.0                         # 进度(0-1)
    total_size: int = 0                           # 要清理的总大小
    cleaned_size: int = 0                         # 已清理的大小
    error_message: Optional[str] = None           # 错误信息
    backup_id: Optional[str] = None               # 备份ID
    
    class Config:
        arbitrary_types_allowed = True


class BackupInfo(BaseModel):
    """备份信息模型"""
    backup_id: str                                # 备份ID
    created_time: datetime                        # 创建时间
    task_id: Optional[str] = None                 # 关联的任务ID
    files: List[Dict] = Field(default_factory=list)  # 备份的文件列表
    backup_path: str                              # 备份存储路径
    total_size: int = 0                           # 总大小
    is_valid: bool = True                         # 备份是否有效
    
    class Config:
        arbitrary_types_allowed = True


class SystemInfo(BaseModel):
    """系统信息模型"""
    c_drive_total: int                            # C盘总容量(字节)
    c_drive_free: int                             # C盘可用空间(字节)
    c_drive_used: int                             # C盘已用空间(字节)
    ram_total: int                                # 总内存(字节)
    ram_available: int                            # 可用内存(字节)
    cpu_usage: float                              # CPU使用率(0-100)
    updated_time: datetime                        # 更新时间
    
    class Config:
        arbitrary_types_allowed = True


class LogEntry(BaseModel):
    """日志条目模型"""
    id: int                                       # 日志ID
    timestamp: datetime                           # 时间戳
    level: str                                    # 日志级别
    message: str                                  # 日志消息
    module: str                                   # 所属模块
    function: Optional[str] = None                # 所属函数
    task_id: Optional[str] = None                 # 关联任务ID
    details: Dict = Field(default_factory=dict)   # 详细信息
    
    class Config:
        arbitrary_types_allowed = True