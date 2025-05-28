#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
任务管理器 - 管理扫描和清理任务
"""

import uuid
import time
from typing import List, Dict, Optional, Union, Any, Tuple
from datetime import datetime
from pathlib import Path
from loguru import logger

# New imports
from services.ai_planner import AIPlannerService
# from services.logger import LoggerService # Moved to avoid circular import

from core.scanner import Scanner
from core.cleaner import Cleaner
from core.rules import RuleManager
from core.rollback import Rollback
from data.models import FileItem, ScanResult, CleanTask, CleanCategory
from data.database import Database
from config.manager import ConfigManager


class TaskManager:
    """任务管理器类，统一管理扫描和清理任务"""

    def __init__(self, config_manager: Optional[ConfigManager] = None, database: Optional[Database] = None, ai_planner_service: Optional[AIPlannerService] = None):
        """初始化任务管理器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
            database: 数据库实例，如果为None则创建新实例
            ai_planner_service: AI规划服务实例，如果为None则尝试创建新实例
        """
        # 类型检查和自动转换
        if isinstance(config_manager, str):
            config_manager = ConfigManager(config_manager)
        elif config_manager is not None and not isinstance(config_manager, ConfigManager):
            config_manager = ConfigManager()
        self.config = config_manager or ConfigManager()
        self.db = database or Database()

        # 初始化日志服务和任务管理器的日志记录器
        try:
            from services.logger import LoggerService  # Delayed import to avoid circular import
            self.logger_service = LoggerService(config_manager=self.config, database=self.db)
            self.logger = self.logger_service.get_logger(__name__)
        except Exception as e:
            self.logger = logger # Use global loguru logger as fallback
            self.logger.error(f"TaskManager failed to initialize its own LoggerService, falling back to global logger: {e}", exc_info=True)

        # 初始化AI规划服务
        if ai_planner_service:
            self.ai_planner = ai_planner_service
            self.logger.info("TaskManager received pre-initialized AIPlannerService.")
        else:
            self.logger.warning("TaskManager did not receive AIPlannerService, attempting to initialize it internally.")
            try:
                self.ai_planner = AIPlannerService(config_manager=self.config)
            except Exception as e:
                self.logger.error(f"TaskManager failed to initialize AIPlannerService internally: {e}", exc_info=True)
                self.ai_planner = None

        # 初始化子模块
        self.scanner = Scanner(config_manager=self.config) # Explicitly pass config_manager
        self.cleaner = Cleaner(config_manager=self.config) # Explicitly pass config_manager
        self.rule_manager = RuleManager(config_manager=self.config) # Explicitly pass config_manager
        self.rollback = Rollback(config_manager=self.config) # Explicitly pass config_manager

        # 当前活动的任务
        self.current_scan_id: Optional[str] = None # Type hint added
        self.current_clean_id: Optional[str] = None # Type hint added
        self.current_ai_task_id: Optional[str] = None # Added for AI-driven tasks
    
    def start_ai_planned_task(self, user_goal: str, current_context: Optional[Dict[str, Any]] = None, precomputed_plan: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        启动一个由AI规划器编排的任务。
        使用AI生成计划，然后尝试执行计划中的步骤。

        Args:
            user_goal: 用户的高级别目标 (例如, "清理我的C盘")。
            current_context: 可选字典，包含相关的系统状态或先前的操作。
            precomputed_plan: 可选字典，如果提供，则使用此预计算的计划而不是重新生成。

        Returns:
            AI驱动的元任务ID，如果规划或执行失败则返回None。
        """
        if not self.ai_planner:
            self.logger.error("AIPlannerService 未初始化，无法启动AI规划任务。")
            return None

        self.current_ai_task_id = f"ai_task_{uuid.uuid4()}"
        self.logger.info(f"启动AI规划任务 ({self.current_ai_task_id}): {user_goal}")

        plan: Optional[Dict[str, Any]] = None

        if precomputed_plan and isinstance(precomputed_plan, dict) and precomputed_plan.get("steps"):
            self.logger.info(f"AI规划任务 {self.current_ai_task_id}: 使用预计算的计划。")
            plan = precomputed_plan
        else:
            if precomputed_plan:
                self.logger.warning(f"AI规划任务 {self.current_ai_task_id}: 提供的预计算计划无效或为空，将重新生成计划。预计算计划: {precomputed_plan}")
            self.logger.info(f"AI规划任务 {self.current_ai_task_id}: 正在为目标 '{user_goal}' 生成新计划。")
            try:
                plan = self.ai_planner.generate_plan(user_goal=user_goal, current_context=current_context)
            except Exception as e:
                self.logger.error(f"AI规划任务 {self.current_ai_task_id}: 生成计划时发生错误: {e}", exc_info=True)
                return None

        if not plan or not isinstance(plan, dict) or "steps" not in plan or not isinstance(plan.get("steps"), list):
            self.logger.error(f"AI规划任务 {self.current_ai_task_id}: AI规划器未能为目标 '{user_goal}' 生成有效计划或计划格式不正确。收到的计划: {plan}")
            return None

        self.logger.info(f"AI规划任务 {self.current_ai_task_id} 收到AI计划: {plan}")
        
        # === 本地补全 action 字段 ===
        import os
        compress_exts = ('.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.cab', '.arj', '.lzh', '.z', '.ace', '.uue', '.jar', '.apk', '.tar.gz', '.tar.bz2', '.tar.xz')
        for step in plan.get("steps", []):
            if "action" not in step or not step["action"]:
                path = step.get("path")
                safety = step.get("safety")
                if not path or safety == "forbid":
                    step["action"] = None
                elif os.path.isdir(path):
                    step["action"] = "delete_dir"
                elif os.path.isfile(path):
                    step["action"] = "delete_file"
                elif isinstance(path, str) and path.lower().endswith(compress_exts):
                    step["action"] = "delete_file"
                else:
                    # 路径不存在，无法判断，action为None
                    step["action"] = None

        # === 聊天功能：如果steps为空，尝试输出chat内容 ===
        if not plan.get("steps"):
            chat = plan.get("chat")
            if chat:
                self.logger.info(f"AI聊天内容: {chat}")
            else:
                self.logger.info("AI未提供清理建议，请检查输入或重试。")

        last_scan_id: Optional[str] = None # To store the ID of the most recent scan action

        for step_num, step in enumerate(plan.get("steps", [])):
            action = step.get("action")
            parameters = step.get("parameters", {})
            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}/{len(plan['steps'])}: 执行 '{action}'，参数: {parameters}")

            try:
                if action == "scan_paths":
                    scan_paths_param = parameters.get("paths")
                    exclude_paths_param = parameters.get("exclude_paths")
                    
                    if not scan_paths_param: # If AI doesn't specify, use config defaults
                        scan_paths_param = self.config.get("scanner.include_dirs", [])
                    if not exclude_paths_param: # If AI doesn't specify, use config defaults
                        exclude_paths_param = self.config.get("scanner.exclude_dirs", [])

                    scan_id = self.start_scan(scan_paths=scan_paths_param, exclude_paths=exclude_paths_param)
                    if scan_id:
                        last_scan_id = scan_id # Store this scan_id
                        self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: '{action}' 启动扫描: {scan_id}")
                        while self.is_scan_active():
                            time.sleep(1) # Wait a bit before checking progress
                            progress_data = self.get_scan_progress()
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 扫描 {scan_id} 进行中 - {progress_data.get('progress', 0.0)*100:.2f}%")
                        
                        self.save_scan_result() 
                        scan_result_check = self.get_scan_result(scan_id)
                        if scan_result_check and scan_result_check.is_complete:
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 扫描 {scan_id} 已完成。")
                        else:
                            self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 扫描 {scan_id} 未成功完成或未找到结果。")
                    else:
                        self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: '{action}' 启动扫描失败。")

                elif action == "perform_cleanup":
                    if not last_scan_id:
                        self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: '{action}' 需要一个 scan_id，但当前没有可用的。")
                        continue

                    categories_to_clean = parameters.get("categories")
                    create_backup_param = parameters.get("create_backup")
                    task_name_param = parameters.get("task_name", f"AI_Clean_{self.current_ai_task_id}_Step{step_num+1}")

                    if create_backup_param is None:
                        create_backup_param = self.config.get("safety.backup.enabled", True)
                    
                    clean_task_id = self.start_clean_task(
                        scan_id=last_scan_id,
                        categories=categories_to_clean,
                        create_backup=create_backup_param,
                        task_name=task_name_param
                    )
                    if clean_task_id:
                        self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: '{action}' 启动清理任务: {clean_task_id}")
                        while self.is_clean_active():
                            time.sleep(1)
                            progress_data = self.get_clean_progress()
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 清理 {clean_task_id} 进行中 - {progress_data.get('progress', 0.0)*100:.2f}%")
                        
                        final_clean_task = self.get_clean_task(clean_task_id)
                        if final_clean_task and final_clean_task.status == "completed":
                             self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 清理任务 {clean_task_id} 已完成。")
                        else:
                            status_msg = final_clean_task.status if final_clean_task else "未知"
                            self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 清理任务 {clean_task_id} 未成功完成。状态: {status_msg}")
                    else:
                        self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: '{action}' 启动清理任务失败。")
                
                elif action == "identify_file_categories":
                    self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: AI步骤 '{action}': 计划建议关注类别: {parameters.get('categories')}. 这可能会影响后续的清理选择。")

                elif action == "suggest_deletions":
                    if last_scan_id:
                        scan_result_for_suggestion = self.get_scan_result(last_scan_id)
                        if scan_result_for_suggestion:
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: AI步骤 '{action}': 基于扫描 {last_scan_id} 建议删除。结果包含 {scan_result_for_suggestion.total_items} 个项目。UI应处理呈现。")
                        else:
                            self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: AI步骤 '{action}': 未找到扫描 {last_scan_id} 的结果以建议删除。")
                    else:
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: AI步骤 '{action}': 没有可用的扫描ID来建议删除。")
                
                elif action == "delete":
                    # 兼容AI直接输出的delete动作
                    path = step.get("path")
                    older_than_days = step.get("older_than_days", 90)
                    if not path:
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 'delete' 缺少 path，跳过。")
                        continue
                    try:
                        import os
                        import shutil
                        import time
                        from datetime import datetime, timedelta
                        if os.path.isdir(path):
                            # 只删除目录下90天前的文件/子目录
                            cutoff = time.time() - older_than_days * 24 * 3600
                            deleted_count = 0
                            for root, dirs, files in os.walk(path):
                                for name in files:
                                    file_path = os.path.join(root, name)
                                    try:
                                        if os.path.getmtime(file_path) < cutoff:
                                            os.remove(file_path)
                                            deleted_count += 1
                                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已删除旧文件 {file_path}")
                                    except Exception as e:
                                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 删除文件 {file_path} 失败: {e}")
                                for name in dirs:
                                    dir_path = os.path.join(root, name)
                                    try:
                                        if os.path.getmtime(dir_path) < cutoff:
                                            shutil.rmtree(dir_path, ignore_errors=True)
                                            deleted_count += 1
                                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已删除旧目录 {dir_path}")
                                    except Exception as e:
                                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 删除目录 {dir_path} 失败: {e}")
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 目录 {path} 下共删除 {deleted_count} 个90天前的文件/目录")
                        else:
                            # 单文件直接删除
                            if os.path.exists(path):
                                if os.path.getmtime(path) < time.time() - older_than_days * 24 * 3600:
                                    os.remove(path)
                                    self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已删除旧文件 {path}")
                                else:
                                    self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 文件 {path} 未满90天，未删除")
                    except Exception as e:
                        self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 删除 {path} 失败: {e}")
                
                elif action == "delete_dir":
                    # 删除目录操作
                    path = step.get("path")
                    force_delete = parameters.get("force_delete", False)
                    create_backup = parameters.get("create_backup", True)
                    
                    if not path:
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 'delete_dir' 缺少 path，跳过。")
                        continue
                    
                    if not os.path.exists(path):
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 目录 {path} 不存在，跳过。")
                        continue
                    
                    if not os.path.isdir(path):
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: {path} 不是目录，跳过。")
                        continue
                    
                    try:
                        import os
                        import shutil
                        from pathlib import Path
                        
                        # 创建备份（如果启用）
                        if create_backup:
                            backup_dir = self.config.get("safety.backup.directory", "./backups")
                            backup_path = os.path.join(backup_dir, f"backup_{os.path.basename(path)}_{int(time.time())}")
                            os.makedirs(backup_dir, exist_ok=True)
                            shutil.copytree(path, backup_path)
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已创建目录备份: {backup_path}")
                        
                        # 删除目录
                        if force_delete:
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            shutil.rmtree(path)
                        
                        self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已删除目录 {path}")
                        
                    except Exception as e:
                        self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 删除目录 {path} 失败: {e}")
                
                elif action == "delete_file":
                    # 删除文件操作
                    path = step.get("path")
                    create_backup = parameters.get("create_backup", True)
                    
                    if not path:
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 'delete_file' 缺少 path，跳过。")
                        continue
                    
                    if not os.path.exists(path):
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 文件 {path} 不存在，跳过。")
                        continue
                    
                    if not os.path.isfile(path):
                        self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: {path} 不是文件，跳过。")
                        continue
                    
                    try:
                        import os
                        import shutil
                        from pathlib import Path
                        
                        # 创建备份（如果启用）
                        if create_backup:
                            backup_dir = self.config.get("safety.backup.directory", "./backups")
                            backup_filename = f"backup_{os.path.basename(path)}_{int(time.time())}"
                            backup_path = os.path.join(backup_dir, backup_filename)
                            os.makedirs(backup_dir, exist_ok=True)
                            shutil.copy2(path, backup_path)
                            self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已创建文件备份: {backup_path}")
                        
                        # 删除文件
                        os.remove(path)
                        self.logger.info(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 已删除文件 {path}")
                        
                    except Exception as e:
                        self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 删除文件 {path} 失败: {e}")
                
                else:
                    self.logger.warning(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 未知操作 '{action}'。正在跳过。")

            except Exception as e:
                self.logger.error(f"AI规划任务 {self.current_ai_task_id} - 步骤 {step_num + 1}: 执行 '{action}' 时出错: {e}", exc_info=True)

        self.logger.info(f"AI规划任务 {self.current_ai_task_id} 已完成处理所有计划步骤。")
        return self.current_ai_task_id

    def start_scan(self, scan_paths=None, exclude_paths=None) -> str:
        """启动新的扫描任务
        
        Args:
            scan_paths: 要扫描的路径列表，如果为None则使用配置中的默认路径
            exclude_paths: 要排除的路径列表，如果为None则使用配置中的默认排除路径
            
        Returns:
            扫描任务ID，如果失败则返回空字符串
        """
        # 启动扫描
        scan_id = self.scanner.start_scan(scan_paths, exclude_paths)
        
        if scan_id:
            self.current_scan_id = scan_id
            logger.info(f"扫描任务已启动: {scan_id}")
        else:
            logger.error("启动扫描任务失败")
        
        return scan_id
    
    def get_scan_progress(self) -> Dict:
        """获取当前扫描任务的进度
        
        Returns:
            包含进度信息的字典
        """
        if not self.scanner._is_scanning:
            return {
                "is_running": False,
                "progress": 0.0,
                "total_items": 0,
                "total_size": 0,
                "scan_id": self.current_scan_id
            }
        
        total_items, total_size, progress = self.scanner.get_progress()
        
        return {
            "is_running": True,
            "progress": progress,
            "total_items": total_items,
            "total_size": total_size,
            "scan_id": self.current_scan_id
        }
    
    def stop_scan(self) -> bool:
        """停止当前扫描任务
        
        Returns:
            是否成功停止
        """
        if not self.scanner._is_scanning:
            return False
        
        return self.scanner.stop_scan()
    
    def pause_scan(self) -> bool:
        """暂停当前扫描任务
        
        Returns:
            是否成功暂停
        """
        if not self.scanner._is_scanning:
            return False
        
        return self.scanner.pause_scan()
    
    def resume_scan(self) -> bool:
        """恢复当前扫描任务
        
        Returns:
            是否成功恢复
        """
        if not self.scanner._is_scanning:
            return False
        
        return self.scanner.resume_scan()

    def is_scan_active(self) -> bool:
        """检查扫描任务是否正在活动"""
        return self.scanner.is_scanning()
    
    def save_scan_result(self) -> bool:
        """保存当前扫描结果到数据库
        
        Returns:
            是否保存成功
        """
        if not self.current_scan_id:
            logger.warning("没有活动的扫描任务，无法保存结果")
            return False
        
        scan_result = self.scanner.get_current_result()
        if not scan_result:
            logger.warning("扫描结果为空，无法保存")
            return False
        
        # 保存到数据库
        success = self.db.save_scan_result(scan_result)
        if success:
            logger.info(f"扫描结果已保存到数据库: {scan_result.scan_id}")
        else:
            logger.error(f"保存扫描结果失败: {scan_result.scan_id}")
        
        return success
    
    def get_scan_result(self, scan_id=None) -> Optional[ScanResult]:
        """获取扫描结果
        
        Args:
            scan_id: 扫描ID，如果为None则使用当前扫描ID
            
        Returns:
            扫描结果对象或None
        """
        if scan_id is None:
            scan_id = self.current_scan_id
            
        if not scan_id:
            logger.warning("没有指定扫描ID，无法获取结果")
            return None
        
        # 如果是当前正在进行的扫描，直接从Scanner获取
        if scan_id == self.current_scan_id and self.scanner._is_scanning:
            return self.scanner.get_current_result()
        
        # 否则从数据库获取
        return self.db.get_scan_result(scan_id)
    
    def list_scan_results(self, limit=10, offset=0) -> List[Dict]:
        """列出历史扫描结果
        
        Args:
            limit: 结果数量限制
            offset: 结果偏移量
            
        Returns:
            扫描结果摘要列表
        """
        return self.db.list_scan_results(limit, offset)
    
    def delete_scan_result(self, scan_id: str) -> bool:
        """删除扫描结果
        
        Args:
            scan_id: 扫描ID
            
        Returns:
            是否删除成功
        """
        if scan_id == self.current_scan_id and self.scanner._is_scanning:
            logger.warning("不能删除正在进行的扫描任务结果")
            return False
        
        return self.db.delete_scan_result(scan_id)
    
    def start_clean_task(self, scan_id=None, categories=None, 
                      create_backup=None, task_name=None) -> str:
        """启动新的清理任务
        
        Args:
            scan_id: 扫描ID，如果为None则使用当前扫描ID
            categories: 要清理的类别列表，如果为None则清理所有类别
            create_backup: 是否创建备份，如果为None则使用配置值
            task_name: 任务名称，如果为None则自动生成
            
        Returns:
            清理任务ID，如果失败则返回空字符串
        """
        if scan_id is None:
            scan_id = self.current_scan_id
            
        if not scan_id:
            logger.warning("没有指定扫描ID，无法启动清理任务")
            return ""
        
        # 获取扫描结果
        scan_result = self.get_scan_result(scan_id)
        if not scan_result:
            logger.warning(f"找不到扫描结果: {scan_id}")
            return ""
        
        # 如果扫描尚未完成，不能启动清理
        if not scan_result.is_complete and scan_id == self.current_scan_id and self.scanner._is_scanning:
            logger.warning("扫描尚未完成，不能启动清理任务")
            return ""
        
        # 获取重复文件集，用于 can_delete 判断
        duplicate_sets = scan_result.duplicate_sets
        
        # 过滤要清理的文件
        files_to_clean = scan_result.files
        if categories:
            # 将字符串类别转换为枚举
            target_categories = {CleanCategory(c) for c in categories if c in CleanCategory.__members__}
            files_to_clean = [
                file for file in files_to_clean 
                if file.category in target_categories and self.rule_manager.can_delete(file, duplicate_sets)
            ]
        else:
            files_to_clean = [
                file for file in files_to_clean 
                if self.rule_manager.can_delete(file, duplicate_sets)
            ]
        
        # 如果指定了清理 DUPLICATE_FILES 类别，我们需要特殊处理
        # 确保只删除重复文件中的副本，保留一个
        if categories and CleanCategory.DUPLICATE_FILES in categories:
            duplicate_files_to_clean = []
            for file in scan_result.files: # 重新遍历原始文件列表
                if self.rule_manager.can_delete(file, duplicate_sets): # 检查是否是可删除的重复文件
                    if file not in files_to_clean: # 避免重复添加
                         duplicate_files_to_clean.append(file)
            files_to_clean.extend(duplicate_files_to_clean)
            # 去重，以防万一
            files_to_clean = list({file.path: file for file in files_to_clean}.values())
            

        if not files_to_clean:
            logger.warning("没有符合条件的文件需要清理")
            return ""
        
        # 生成任务名称
        if not task_name:
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_name = f"清理任务_{now}"
        
        # 启动清理任务
        task_id = self.cleaner.start_clean_task(
            files_to_clean=files_to_clean,
            categories=categories,
            task_name=task_name,
            create_backup=create_backup
        )
        
        if task_id:
            self.current_clean_id = task_id
            
            # 将清理任务保存到数据库
            task = self.cleaner.get_current_task()
            if task:
                task.scan_id = scan_id
                self.db.save_clean_task(task)
            
            logger.info(f"清理任务已启动: {task_id}")
        else:
            logger.error("启动清理任务失败")
        
        return task_id
    
    def get_clean_progress(self) -> Dict:
        """获取当前清理任务的进度
        
        Returns:
            包含进度信息的字典
        """
        if not self.cleaner._is_cleaning:
            return {
                "is_running": False,
                "progress": 0.0,
                "cleaned_size": 0,
                "total_size": 0,
                "task_id": self.current_clean_id
            }
        
        cleaned_size, total_size, progress = self.cleaner.get_progress()
        
        return {
            "is_running": True,
            "progress": progress,
            "cleaned_size": cleaned_size,
            "total_size": total_size,
            "task_id": self.current_clean_id
        }
    
    def stop_clean_task(self) -> bool:
        """停止当前清理任务
        
        Returns:
            是否成功停止
        """
        if not self.cleaner._is_cleaning:
            return False
        
        result = self.cleaner.stop_clean_task()
        
        # 更新数据库中的任务状态
        if result and self.current_clean_id:
            task = self.cleaner.get_current_task()
            if task:
                self.db.save_clean_task(task)
        
        return result

    def is_clean_active(self) -> bool:
        """检查清理任务是否正在活动"""
        return self.cleaner.is_cleaning()
    
    def pause_clean_task(self) -> bool:
        """暂停当前清理任务
        
        Returns:
            是否成功暂停
        """
        if not self.cleaner._is_cleaning:
            return False
        
        result = self.cleaner.pause_clean_task()
        
        # 更新数据库中的任务状态
        if result and self.current_clean_id:
            task = self.cleaner.get_current_task()
            if task:
                self.db.save_clean_task(task)
        
        return result

    def is_clean_active(self) -> bool:
        """检查清理任务是否正在活动"""
        return self.cleaner.is_cleaning()
    
    def resume_clean_task(self) -> bool:
        """恢复当前清理任务
        
        Returns:
            是否成功恢复
        """
        if not self.cleaner._is_cleaning:
            return False
        
        result = self.cleaner.resume_clean_task()
        
        # 更新数据库中的任务状态
        if result and self.current_clean_id:
            task = self.cleaner.get_current_task()
            if task:
                self.db.save_clean_task(task)
        
        return result

    def is_clean_active(self) -> bool:
        """检查清理任务是否正在活动"""
        return self.cleaner.is_cleaning()
    
    def get_clean_task(self, task_id=None) -> Optional[CleanTask]:
        """获取清理任务
        
        Args:
            task_id: 任务ID，如果为None则使用当前任务ID
            
        Returns:
            清理任务对象或None
        """
        if task_id is None:
            task_id = self.current_clean_id
            
        if not task_id:
            logger.warning("没有指定任务ID，无法获取任务")
            return None
        
        # 如果是当前正在进行的任务，直接从Cleaner获取
        if task_id == self.current_clean_id and self.cleaner._is_cleaning:
            return self.cleaner.get_current_task()
        
        # 否则从数据库获取
        return self.db.get_clean_task(task_id)
    
    def list_clean_tasks(self, limit=10, offset=0) -> List[Dict]:
        """列出历史清理任务
        
        Args:
            limit: 结果数量限制
            offset: 结果偏移量
            
        Returns:
            清理任务摘要列表
        """
        return self.db.list_clean_tasks(limit, offset)
    
    def delete_clean_task(self, task_id: str) -> bool:
        """删除清理任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否删除成功
        """
        if task_id == self.current_clean_id and self.cleaner._is_cleaning:
            logger.warning("不能删除正在进行的清理任务")
            return False
        
        return self.db.delete_clean_task(task_id)
    
    def restore_from_backup(self, backup_id: str, selected_files=None) -> bool:
        """从备份还原文件
        
        Args:
            backup_id: 备份ID
            selected_files: 要还原的文件路径列表，如果为None则还原所有文件
            
        Returns:
            是否成功还原
        """
        return self.rollback.restore_backup(backup_id, selected_files)
    
    def list_backups(self) -> List[Dict]:
        """列出所有可用的备份
        
        Returns:
            备份信息列表
        """
        return self.rollback.list_backups()
    
    def delete_backup(self, backup_id: str) -> bool:
        """删除备份
        
        Args:
            backup_id: 备份ID
            
        Returns:
            是否成功删除
        """
        return self.rollback.delete_backup(backup_id)
    
    def clean_old_backups(self, days=None) -> int:
        """清理旧备份
        
        Args:
            days: 保留天数，如果为None则使用配置值
            
        Returns:
            清理的备份数量
        """
        return self.rollback.clean_old_backups(days)
    
    def close(self):
        """关闭任务管理器，释放资源"""
        self.logger.info("开始关闭任务管理器...")

        # 停止进行中的任务
        if hasattr(self, 'scanner') and self.scanner and self.scanner._is_scanning: 
            self.logger.info("停止扫描任务...")
            self.scanner.stop_scan()

        if hasattr(self, 'cleaner') and self.cleaner and self.cleaner._is_cleaning: 
            self.logger.info("停止清理任务...")
            self.cleaner.stop_clean_task()

        # 关闭日志服务 (if it was initialized)
        if hasattr(self, 'logger_service') and self.logger_service:
            try:
                self.logger.info("关闭日志服务...")
                self.logger_service.close()
            except Exception as e:
                # Use global logger if self.logger might not be available
                fallback_logger = logger if not hasattr(self, 'logger') else self.logger
                fallback_logger.error(f"关闭LoggerService时出错: {e}", exc_info=True)
        
        # 关闭数据库连接 (if it was initialized and not already closed by LoggerService)
        # LoggerService might share the db instance, so check if it's still open
        # and if self.db was initialized in the first place.
        if hasattr(self, 'db') and self.db and hasattr(self.db, 'conn') and self.db.conn: 
             try:
                self.logger.info("关闭数据库连接...")
                self.db.close()
             except Exception as e:
                fallback_logger = logger if not hasattr(self, 'logger') else self.logger
                fallback_logger.error(f"关闭TaskManager中的数据库时出错: {e}", exc_info=True)

        # Use global logger if self.logger is not available (e.g. during __init__ failure)
        final_logger = logger if not hasattr(self, 'logger') else self.logger
        final_logger.info("任务管理器已关闭")