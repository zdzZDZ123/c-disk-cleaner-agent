#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
报告服务 - 生成清理报告和分析报告
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from loguru import logger

from services.logger import LoggerService
from data.models import ScanResult, CleanTask
from data.database import Database
from config.manager import ConfigManager

class ReportService:
    """报告服务类，用于生成各种清理和分析报告"""

    def __init__(self, config_manager: Optional[ConfigManager] = None, database: Optional[Database] = None):
        """初始化报告服务
        
        Args:
            config_manager: 配置管理器实例
            database: 数据库实例
        """
        self.config = config_manager or ConfigManager()
        self.db = database or Database()
        
        # 初始化日志服务
        try:
            self.logger_service = LoggerService(config_manager=self.config, database=self.db)
            self.logger = self.logger_service.get_logger(__name__)
        except Exception as e:
            self.logger = logger
            self.logger.error(f"ReportService failed to initialize LoggerService: {e}")

        # 创建报告输出目录
        self.report_dir = Path(self.config.get("reports.output_dir", "reports"))
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate_cleanup_report(self, clean_task_id: str) -> Optional[Dict[str, Any]]:
        """生成清理任务报告
        
        Args:
            clean_task_id: 清理任务ID
            
        Returns:
            包含报告数据的字典，如果生成失败则返回None
        """
        try:
            # 获取清理任务信息
            clean_task = self.db.get_clean_task(clean_task_id)
            if not clean_task:
                self.logger.error(f"清理任务 {clean_task_id} 不存在")
                return None

            # 获取扫描结果
            scan_result = self.db.get_scan_result(clean_task.scan_id)
            if not scan_result:
                self.logger.error(f"扫描结果 {clean_task.scan_id} 不存在")
                return None

            # 生成报告数据
            report_data = {
                "task_id": clean_task_id,
                "task_name": clean_task.task_name,
                "start_time": clean_task.start_time.isoformat(),
                "end_time": clean_task.end_time.isoformat() if clean_task.end_time else None,
                "status": clean_task.status,
                "total_files_cleaned": clean_task.total_files_cleaned,
                "total_space_freed": clean_task.total_space_freed,
                "categories_cleaned": clean_task.categories_cleaned,
                "backup_created": clean_task.backup_created,
                "backup_id": clean_task.backup_id,
                "scan_summary": {
                    "total_items": scan_result.total_items,
                    "total_size": scan_result.total_size,
                    "scan_paths": scan_result.scan_paths,
                    "scan_time": scan_result.scan_time.isoformat()
                }
            }

            # 生成报告文件
            report_file = self.report_dir / f"cleanup_report_{clean_task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"清理报告已生成: {report_file}")
            return report_data

        except Exception as e:
            self.logger.error(f"生成清理报告时发生错误: {e}")
            return None

    def generate_space_analysis_report(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """生成空间使用分析报告
        
        Args:
            scan_id: 扫描ID
            
        Returns:
            包含分析数据的字典，如果生成失败则返回None
        """
        try:
            # 获取扫描结果
            scan_result = self.db.get_scan_result(scan_id)
            if not scan_result:
                self.logger.error(f"扫描结果 {scan_id} 不存在")
                return None

            # 分析文件类型分布
            file_types = {}
            for item in scan_result.items:
                ext = os.path.splitext(item.path)[1].lower() or "无扩展名"
                if ext not in file_types:
                    file_types[ext] = {"count": 0, "size": 0}
                file_types[ext]["count"] += 1
                file_types[ext]["size"] += item.size

            # 生成分析数据
            analysis_data = {
                "scan_id": scan_id,
                "scan_time": scan_result.scan_time.isoformat(),
                "total_items": scan_result.total_items,
                "total_size": scan_result.total_size,
                "file_type_distribution": file_types,
                "largest_files": sorted(
                    [{"path": item.path, "size": item.size} for item in scan_result.items],
                    key=lambda x: x["size"],
                    reverse=True
                )[:10]  # 前10个最大文件
            }

            # 生成报告文件
            report_file = self.report_dir / f"space_analysis_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, ensure_ascii=False, indent=2)

            # 生成可视化图表
            self._generate_space_visualization(analysis_data, scan_id)

            self.logger.info(f"空间分析报告已生成: {report_file}")
            return analysis_data

        except Exception as e:
            self.logger.error(f"生成空间分析报告时发生错误: {e}")
            return None

    def _generate_space_visualization(self, analysis_data: Dict[str, Any], scan_id: str):
        """生成空间使用可视化图表
        
        Args:
            analysis_data: 分析数据
            scan_id: 扫描ID
        """
        try:
            # 创建图表目录
            charts_dir = self.report_dir / "charts"
            charts_dir.mkdir(parents=True, exist_ok=True)

            # 文件类型分布饼图
            plt.figure(figsize=(10, 6))
            file_types = analysis_data["file_type_distribution"]
            sizes = [data["size"] for data in file_types.values()]
            labels = [f"{ext} ({data['count']}个文件)" for ext, data in file_types.items()]
            plt.pie(sizes, labels=labels, autopct='%1.1f%%')
            plt.title("文件类型分布")
            plt.savefig(charts_dir / f"file_type_distribution_{scan_id}.png")
            plt.close()

            # 最大文件条形图
            plt.figure(figsize=(12, 6))
            largest_files = analysis_data["largest_files"]
            file_names = [os.path.basename(f["path"]) for f in largest_files]
            file_sizes = [f["size"] / (1024 * 1024) for f in largest_files]  # 转换为MB
            plt.barh(file_names, file_sizes)
            plt.title("最大文件TOP10")
            plt.xlabel("大小 (MB)")
            plt.tight_layout()
            plt.savefig(charts_dir / f"largest_files_{scan_id}.png")
            plt.close()

        except Exception as e:
            self.logger.error(f"生成可视化图表时发生错误: {e}")

    def list_reports(self, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有报告
        
        Args:
            report_type: 报告类型（可选），如 'cleanup' 或 'space_analysis'
            
        Returns:
            报告列表
        """
        try:
            reports = []
            for file in self.report_dir.glob("*.json"):
                if report_type and not file.name.startswith(report_type):
                    continue
                
                with open(file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                    reports.append({
                        "file_name": file.name,
                        "file_path": str(file),
                        "created_time": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
                        "report_type": "cleanup" if "cleanup_report" in file.name else "space_analysis",
                        "data": report_data
                    })
            
            return sorted(reports, key=lambda x: x["created_time"], reverse=True)
        except Exception as e:
            self.logger.error(f"列出报告时发生错误: {e}")
            return []

    def delete_report(self, report_file: str) -> bool:
        """删除报告文件
        
        Args:
            report_file: 报告文件名
            
        Returns:
            是否成功删除
        """
        try:
            file_path = self.report_dir / report_file
            if file_path.exists():
                file_path.unlink()
                self.logger.info(f"报告文件已删除: {file_path}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除报告文件时发生错误: {e}")
            return False

    def generate_comparison_report(self, scan_id: str, clean_task_id: str) -> Optional[Dict[str, Any]]:
        """生成清理前后对比报告
        Args:
            scan_id: 清理前的扫描ID
            clean_task_id: 清理任务ID
        Returns:
            对比报告字典
        """
        try:
            scan_result = self.db.get_scan_result(scan_id)
            clean_task = self.db.get_clean_task(clean_task_id)
            if not scan_result or not clean_task:
                self.logger.error(f"无法获取对比报告所需数据: scan_id={scan_id}, clean_task_id={clean_task_id}")
                return None
            # 清理前
            before_total_size = scan_result.total_size
            before_total_items = scan_result.total_items
            before_by_category = scan_result.by_category
            # 清理后
            after_cleaned_size = clean_task.cleaned_size
            after_total_size = before_total_size - after_cleaned_size
            after_total_items = before_total_items - len(clean_task.files_to_clean)
            # 各类别变化
            category_changes = {}
            for cat, size in before_by_category.items():
                cleaned = 0
                if clean_task.categories and cat in clean_task.categories:
                    cleaned = size if after_cleaned_size > 0 else 0
                category_changes[cat] = {
                    "before": size,
                    "after": size - cleaned,
                    "cleaned": cleaned
                }
            # 释放空间TOP5
            top_cleaned = sorted(
                [(cat, v["cleaned"]) for cat, v in category_changes.items()],
                key=lambda x: x[1], reverse=True
            )[:5]
            # 详细变化
            detail = {
                "files_cleaned": clean_task.files_to_clean,
                "categories": clean_task.categories,
                "backup_id": clean_task.backup_id
            }
            report = {
                "scan_id": scan_id,
                "clean_task_id": clean_task_id,
                "before_total_size": before_total_size,
                "after_total_size": after_total_size,
                "before_total_items": before_total_items,
                "after_total_items": after_total_items,
                "total_cleaned_size": after_cleaned_size,
                "category_changes": category_changes,
                "top_cleaned_categories": top_cleaned,
                "detail": detail,
                "generated_time": datetime.now().isoformat()
            }
            # 保存报告
            report_file = self.report_dir / f"comparison_report_{scan_id}_{clean_task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"清理前后对比报告已生成: {report_file}")
            return report
        except Exception as e:
            self.logger.error(f"生成清理前后对比报告时发生错误: {e}")
            return None 