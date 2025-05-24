#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
调度器服务 - 管理定时任务和系统资源监控
"""

import os
import time
import threading
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from data.models import SystemInfo
from config.manager import ConfigManager
from services.task_manager import TaskManager


class SchedulerService:
    """调度器服务类，负责定时任务和系统监控"""
    
    def __init__(self, config_manager=None, task_manager=None):
        """初始化调度器服务
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
            task_manager: 任务管理器实例，如果为None则创建新实例
        """
        self.config = config_manager or ConfigManager()
        self.task_manager = task_manager or TaskManager()
        
        # 初始化调度器
        self.scheduler = BackgroundScheduler()
        
        # 系统信息
        self.system_info = self._get_system_info()
        
        # 已注册的任务ID
        self.job_ids = []
    
    def start(self):
        """启动调度器"""
        # 先清理已有任务
        for job_id in self.job_ids:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
        
        self.job_ids = []
        
        # 注册系统监控任务
        self._register_system_monitor()
        
        # 注册自动扫描任务
        self._register_auto_scan()
        
        # 注册自动清理任务
        self._register_auto_clean()
        
        # 注册自动清理旧备份任务
        self._register_cleanup_old_backups()
        
        # 注册自动清理日志任务
        self._register_cleanup_logs()
        
        # 启动调度器
        self.scheduler.start()
        logger.info("调度器服务已启动")
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
        logger.info("调度器服务已停止")
    
    def add_task(self, job_id: str, func: Callable, trigger: Any, **kwargs):
        """添加任务
        
        Args:
            job_id: 任务ID
            func: 任务函数
            trigger: 触发器
            **kwargs: 其他参数
        """
        if job_id in self.job_ids:
            # 如果任务已存在，先移除
            self.scheduler.remove_job(job_id)
        
        self.scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs
        )
        
        self.job_ids.append(job_id)
        logger.info(f"已添加任务: {job_id}")
    
    def remove_task(self, job_id: str):
        """移除任务
        
        Args:
            job_id: 任务ID
        """
        if job_id in self.job_ids:
            self.scheduler.remove_job(job_id)
            self.job_ids.remove(job_id)
            logger.info(f"已移除任务: {job_id}")
    
    def get_system_info(self) -> SystemInfo:
        """获取系统信息
        
        Returns:
            系统信息对象
        """
        return self.system_info
    
    def update_system_info(self):
        """更新系统信息"""
        self.system_info = self._get_system_info()
        
        # 检查磁盘空间是否不足
        if self._check_low_disk_space():
            # 如果不足，启动扫描
            self._handle_low_disk_space()
    
    def _get_system_info(self) -> SystemInfo:
        """获取系统信息
        
        Returns:
            系统信息对象
        """
        try:
            # 获取C盘信息
            c_disk = psutil.disk_usage("C:\\")
            
            # 获取内存信息
            memory = psutil.virtual_memory()
            
            # 获取CPU使用率
            cpu_usage = psutil.cpu_percent(interval=0.1)
            
            return SystemInfo(
                c_drive_total=c_disk.total,
                c_drive_free=c_disk.free,
                c_drive_used=c_disk.used,
                ram_total=memory.total,
                ram_available=memory.available,
                cpu_usage=cpu_usage,
                updated_time=datetime.now()
            )
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            # 返回一个空对象
            return SystemInfo(
                c_drive_total=0,
                c_drive_free=0,
                c_drive_used=0,
                ram_total=0,
                ram_available=0,
                cpu_usage=0.0,
                updated_time=datetime.now()
            )
    
    def _check_low_disk_space(self) -> bool:
        """检查是否磁盘空间不足
        
        Returns:
            是否空间不足
        """
        # 如果未启用磁盘不足检测，直接返回False
        if not self.config.get("schedule.scan_on_low_disk.enabled", True):
            return False
        
        # 获取阈值
        threshold_percent = self.config.get("schedule.scan_on_low_disk.threshold_percent", 10)
        
        # 计算剩余空间百分比
        if self.system_info.c_drive_total > 0:
            free_percent = (self.system_info.c_drive_free / self.system_info.c_drive_total) * 100
            return free_percent < threshold_percent
        
        return False
    
    def _handle_low_disk_space(self):
        """处理磁盘空间不足的情况"""
        logger.warning(f"C盘空间不足，剩余 {self.system_info.c_drive_free / (1024*1024*1024):.2f} GB")
        
        # 检查是否有扫描或清理任务正在运行
        if self.task_manager.scanner._is_scanning or self.task_manager.cleaner._is_cleaning:
            logger.info("有任务正在运行，跳过自动扫描")
            return
        
        # 启动一次扫描任务
        logger.info("自动启动扫描任务")
        self.task_manager.start_scan()
    
    def _register_system_monitor(self):
        """注册系统监控任务"""
        # 每5分钟更新一次系统信息
        self.add_task(
            job_id="system_monitor",
            func=self.update_system_info,
            trigger=IntervalTrigger(minutes=5)
        )
    
    def _register_auto_scan(self):
        """注册自动扫描任务"""
        # 检查是否启用
        if not self.config.get("schedule.auto_scan.enabled", False):
            return
        
        # 获取间隔天数
        interval_days = self.config.get("schedule.auto_scan.interval_days", 7)
        
        # 设置每天凌晨3点执行
        self.add_task(
            job_id="auto_scan",
            func=self._run_auto_scan,
            trigger=CronTrigger(hour=3, minute=0),
            kwargs={"interval_days": interval_days}
        )
    
    def _register_auto_clean(self):
        """注册自动清理任务"""
        # 检查是否启用
        if not self.config.get("schedule.auto_clean.enabled", False):
            return
        
        # 获取间隔天数
        interval_days = self.config.get("schedule.auto_clean.interval_days", 14)
        
        # 设置每天凌晨4点执行
        self.add_task(
            job_id="auto_clean",
            func=self._run_auto_clean,
            trigger=CronTrigger(hour=4, minute=0),
            kwargs={"interval_days": interval_days}
        )
    
    def _register_cleanup_old_backups(self):
        """注册清理旧备份任务"""
        # 每周日凌晨2点执行
        self.add_task(
            job_id="cleanup_old_backups",
            func=self._run_cleanup_old_backups,
            trigger=CronTrigger(day_of_week="sun", hour=2, minute=0)
        )
    
    def _register_cleanup_logs(self):
        """注册清理日志任务"""
        # 每周日凌晨1点执行
        self.add_task(
            job_id="cleanup_logs",
            func=self._run_cleanup_logs,
            trigger=CronTrigger(day_of_week="sun", hour=1, minute=0)
        )
    
    def _run_auto_scan(self, interval_days: int):
        """运行自动扫描任务
        
        Args:
            interval_days: 扫描间隔天数
        """
        # 检查上次扫描时间
        try:
            # 获取最近的扫描结果
            recent_scans = self.task_manager.list_scan_results(limit=1)
            
            if recent_scans:
                last_scan_time = recent_scans[0]["start_time"]
                days_since_last = (datetime.now() - last_scan_time).days
                
                # 如果距离上次扫描不足间隔天数，则跳过
                if days_since_last < interval_days:
                    logger.info(f"距离上次扫描仅 {days_since_last} 天，未达到间隔 {interval_days} 天，跳过自动扫描")
                    return
            
            # 检查是否有任务正在运行
            if self.task_manager.scanner._is_scanning or self.task_manager.cleaner._is_cleaning:
                logger.info("有任务正在运行，跳过自动扫描")
                return
            
            # 启动扫描任务
            logger.info("自动启动扫描任务")
            self.task_manager.start_scan()
            
        except Exception as e:
            logger.error(f"自动扫描任务失败: {e}")
    
    def _run_auto_clean(self, interval_days: int):
        """运行自动清理任务
        
        Args:
            interval_days: 清理间隔天数
        """
        # 检查上次清理时间
        try:
            # 获取最近的清理任务
            recent_tasks = self.task_manager.list_clean_tasks(limit=1)
            
            if recent_tasks:
                last_clean_time = recent_tasks[0]["created_time"]
                days_since_last = (datetime.now() - last_clean_time).days
                
                # 如果距离上次清理不足间隔天数，则跳过
                if days_since_last < interval_days:
                    logger.info(f"距离上次清理仅 {days_since_last} 天，未达到间隔 {interval_days} 天，跳过自动清理")
                    return
            
            # 检查是否有任务正在运行
            if self.task_manager.scanner._is_scanning or self.task_manager.cleaner._is_cleaning:
                logger.info("有任务正在运行，跳过自动清理")
                return
            
            # 获取最近的扫描结果
            recent_scans = self.task_manager.list_scan_results(limit=1)
            if not recent_scans:
                logger.info("没有可用的扫描结果，跳过自动清理")
                return
            
            # 启动清理任务，清理临时文件和缓存
            logger.info("自动启动清理任务")
            categories = [
                "temp_files",
                "browser_cache",
                "windows_cache"
            ]
            self.task_manager.start_clean_task(
                scan_id=recent_scans[0]["scan_id"],
                categories=categories,
                create_backup=True
            )
            
        except Exception as e:
            logger.error(f"自动清理任务失败: {e}")
    
    def _run_cleanup_old_backups(self):
        """运行清理旧备份任务"""
        try:
            # 获取保留天数
            retention_days = self.config.get("safety.backup.retention_days", 30)
            
            # 清理旧备份
            count = self.task_manager.clean_old_backups(retention_days)
            logger.info(f"已清理 {count} 个过期备份")
            
        except Exception as e:
            logger.error(f"清理旧备份任务失败: {e}")
    
    def _run_cleanup_logs(self):
        """运行清理日志任务"""
        try:
            # 清理30天前的日志
            from data.database import Database
            db = Database()
            count = db.clear_logs(30)
            db.close()
            
            logger.info(f"已清理 {count} 条过期日志")
            
        except Exception as e:
            logger.error(f"清理日志任务失败: {e}")
    
    def close(self):
        """关闭调度器服务"""
        self.stop()
        if self.task_manager:
            self.task_manager.close()
        logger.info("调度器服务已关闭") 