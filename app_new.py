#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
C盘清理工具 - 主应用程序入口
Based on README.md specifications.
支持多种AI模型（Gemini、Qwen、文心一言）生成清理计划
"""

import argparse
import sys
import time
import signal
import os  # Needed for potential size calculation in list-duplicates
from pathlib import Path

# Assume these modules exist based on README.md project structure
# We'll wrap the imports in try-except to allow basic execution even if modules are missing
try:
    from config.manager import ConfigManager
    from services.logger import LoggerService
    from services.task_manager import TaskManager
    from services.scheduler import SchedulerService
    from services.ai_planner import AIPlannerService
    # Database might be implicitly used by TaskManager, so direct import might not be needed here
    # from data.database import Database 
    MODULE_ERROR = None
except ImportError as e:
    MODULE_ERROR = e
    # Define dummy classes/functions if imports fail, to allow basic script execution/help message
    class ConfigManager: pass
    class LoggerService:
        def __init__(self, config): pass
        def get_logger(self):
            import logging
            # Basic logger if service fails
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            return logging.getLogger(__name__)
    class TaskManager:
        def __init__(self, config, db=None): pass
        def start_scan(self, scan_paths, exclude_paths): return None
        def start_clean_task(self, scan_id, categories, create_backup): return None
        def restore_from_backup(self, backup_id): return False
        def list_backups(self): return []
        def get_scan_result(self, scan_id): return None
        def stop_scan(self): pass
        def stop_clean_task(self): pass
        def get_scan_progress(self): return {'progress': 0, 'total_items': 0, 'total_size': 0}
        def get_clean_progress(self): return {'progress': 0, 'cleaned_size': 0, 'total_size': 0}
        def get_clean_task(self, task_id): return None # Should return an object with cleaned_size, backup_id etc.
        class Scanner: _is_scanning = False # Dummy attribute
        class Cleaner: _is_cleaning = False # Dummy attribute
        scanner = Scanner()
        cleaner = Cleaner()
        
    class SchedulerService:
        def __init__(self, config, task_manager): pass
        def start(self): pass
        def close(self): pass
        def update_system_info(self): pass # Added based on previous code
        
    class AIPlannerService:
        def __init__(self, config_manager=None, model=None): pass
        def generate_plan(self, user_goal, current_context=None): return None
        def get_available_models(self): return []
        def set_model(self, model): return False

# --- Global Application Context ---
# Using a simple dictionary for context instead of a full class for this rewrite
app_context = {
    "config": None,
    "logger": None,
    "task_manager": None,
    "scheduler": None,
    "ai_planner": None
}

def initialize_app():
    """Initializes application components based on config."""
    if MODULE_ERROR:
        print(f"错误：无法导入必要的模块: {MODULE_ERROR}", file=sys.stderr)
        print("请确保所有依赖已安装并且项目结构正确。", file=sys.stderr)
        # Still try to initialize logger for basic messages
        app_context["logger"] = LoggerService(None).get_logger()
        return False

    try:
        app_context["config"] = ConfigManager()
        # Assuming LoggerService needs config
        logger_service = LoggerService(app_context["config"]) 
        app_context["logger"] = logger_service.get_logger() 
        
        # Assuming TaskManager needs config (and potentially a DB instance implicitly)
        app_context["task_manager"] = TaskManager(app_context["config"]) 
        
        # Assuming SchedulerService needs config and task_manager
        app_context["scheduler"] = SchedulerService(app_context["config"], app_context["task_manager"])
        
        # Initialize AI Planner Service
        app_context["ai_planner"] = AIPlannerService(app_context["config"])
        
        app_context["logger"].info("应用程序组件初始化成功。")
        return True
    except Exception as e:
        # Use basic print if logger failed
        log_func = print if app_context.get("logger") is None else app_context["logger"].error
        log_func(f"应用程序初始化失败: {e}", file=sys.stderr)
        return False

def cleanup_app():
    """Cleans up resources."""
    logger = app_context.get("logger")
    log_info = print if logger is None else logger.info
    
    log_info("正在关闭应用程序...")
    # Gracefully close services if they exist and have a close method
    if app_context.get("scheduler") and hasattr(app_context["scheduler"], "close"):
        try:
            app_context["scheduler"].close()
            log_info("调度器已关闭。")
        except Exception as e:
            log_info(f"关闭调度器时出错: {e}")
            
    if app_context.get("task_manager") and hasattr(app_context["task_manager"], "close"):
        try:
            app_context["task_manager"].close() # Assuming TaskManager might need cleanup
            log_info("任务管理器已关闭。")
        except Exception as e:
            log_info(f"关闭任务管理器时出错: {e}")
            
    # Add DB closing if TaskManager doesn't handle it
    # if app_context.get("db") and hasattr(app_context["db"], "close"):
    #     app_context["db"].close()
        
    log_info("应用程序已关闭。")

def signal_handler(sig, frame):
    """Handles termination signals gracefully."""
    logger = app_context.get("logger", None)
    log_info = print if logger is None else logger.info
    log_info(f"收到信号 {sig}，准备关闭...")
    cleanup_app()
    sys.exit(0)

def discover_cleanup_dirs():
    """自动发现本机常见可清理目录"""
    candidates = [
        Path.home() / 'Downloads',
        Path.home() / 'AppData' / 'Local' / 'Temp',
        Path('C:/Windows/Temp'),
        Path('C:/$Recycle.Bin'),
        Path.home() / 'Desktop',
    ]
    existing = [str(p) for p in candidates if p.exists()]
    return existing

# --- AI Plan Command Implementation ---
def run_ai_plan(args):
    """使用AI模型生成磁盘清理计划"""
    logger = app_context["logger"]
    ai_planner = app_context["ai_planner"]
    task_manager = app_context["task_manager"]
    
    if not ai_planner:
        logger.error("AI规划服务未初始化，无法生成计划。")
        print("错误：AI规划服务未初始化。请确保配置了有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    
    # 获取可用的AI模型
    available_models = ai_planner.get_available_models()
    if not available_models:
        logger.error("未找到任何可用的AI模型。")
        print("错误：未找到任何可用的AI模型。请确保至少配置了一个有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    
    # 如果指定了模型，则尝试切换到该模型
    if hasattr(args, 'model') and args.model and args.model not in available_models:
        logger.warning(f"指定的模型 '{args.model}' 不可用。可用模型: {', '.join(available_models)}")
        print(f"警告：指定的模型 '{args.model}' 不可用。")
        print(f"可用的模型: {', '.join(available_models)}")
        print(f"将使用默认模型: {ai_planner.current_model}")
    elif hasattr(args, 'model') and args.model:
        success = ai_planner.set_model(args.model)
        if not success:
            logger.warning(f"切换到模型 '{args.model}' 失败。将使用默认模型: {ai_planner.current_model}")
            print(f"警告：切换到模型 '{args.model}' 失败。将使用默认模型: {ai_planner.current_model}")
    
    # 显示当前使用的模型
    print(f"\n使用 {ai_planner.current_model.capitalize()} 模型生成清理计划...\n")
    
    # 获取用户目标
    goal = args.goal if hasattr(args, 'goal') and args.goal else "清理C盘，释放磁盘空间，重点关注临时文件、大文件和重复文件。"
    
    # 获取扫描路径和排除路径
    if hasattr(args, 'paths') and args.paths:
        scan_paths = args.paths.split(',')
        logger.info(f"用户指定分析路径: {scan_paths}")
    else:
        scan_paths = discover_cleanup_dirs()
        if not scan_paths:
            scan_paths = ["C:\\"]
        logger.info(f"自动发现分析路径: {scan_paths}")
    exclude_paths = args.exclude.split(',') if hasattr(args, 'exclude') and args.exclude else []
    logger.info(f"排除路径: {exclude_paths}")
    
    # 获取系统信息作为上下文
    context = {
        "system_info": {
            "os": "Windows",
            "free_disk_space_gb": args.free_space if hasattr(args, 'free_space') and args.free_space else 0
        },
        "user_preferences": {
            "keep_files_newer_than_days": args.keep_days if hasattr(args, 'keep_days') and args.keep_days else 30
        },
        "scan_paths": scan_paths,
        "exclude_paths": exclude_paths,
        "existing_cleanup_dirs": scan_paths if not (hasattr(args, 'paths') and args.paths) else None
    }
    
    # 初始化对话历史列表
    conversation_history = []
    
    # 生成计划循环，直到用户确认计划可行
    plan = None
    plan_confirmed = False
    
    print(f"\n===== 多轮对话交互模式 =====\n")
    print(f"您可以与AI进行多轮对话，细化清理目标或实时调整计划。")
    print(f"输入'确认'接受当前计划，输入'退出'结束对话。\n")
    
    # 添加初始用户目标到对话历史
    conversation_history.append({"role": "user", "content": f"我的目标是：{goal}。请根据这个目标生成一个磁盘清理计划。"})
    
    while not plan_confirmed:
        try:
            print(f"目标: {goal}")
            print("正在生成清理计划，请稍候...")
            
            # 使用对话历史生成计划
            plan = ai_planner.generate_plan(user_goal=goal, current_context=context)
            
            if not plan:
                logger.error("生成清理计划失败。")
                print("错误：生成清理计划失败。请检查API密钥和网络连接。")
                return
            
            # 显示生成的计划
            print("\n生成的清理计划如下：\n")
            
            # 格式化显示计划内容
            if isinstance(plan, dict) and plan.get("steps"):
                print("AI 生成的清理计划:")
                for i, step in enumerate(plan["steps"]):
                    action = step.get('action', '未知动作')
                    description = step.get('description', '')
                    parameters = step.get('parameters', {})
                    print(f"  步骤 {i+1}: {action}")
                    if description:
                        print(f"    描述: {description}")
                    if parameters:
                        print(f"    参数: {parameters}")
                
                # 将AI回复添加到对话历史
                ai_response = "我已根据您的需求生成了清理计划。"
                conversation_history.append({"role": "assistant", "content": ai_response})
            else:
                # 如果计划不是预期的格式，则使用JSON显示
                import json
                print(json.dumps(plan, ensure_ascii=False, indent=2))
                
                # 将AI回复添加到对话历史
                ai_response = "我已生成清理计划，但格式可能与预期不同。"
                conversation_history.append({"role": "assistant", "content": ai_response})
            
            # 询问用户反馈或确认
            try:
                # 检查是否在交互式环境中
                if sys.stdin.isatty():
                    user_input = input("\n请提供反馈或输入'确认'接受计划，输入'退出'结束对话: ").strip()
                    
                    if user_input.lower() == '确认':
                        plan_confirmed = True
                        logger.info("用户确认清理计划可行。")
                        conversation_history.append({"role": "user", "content": "我确认这个计划可行。"})
                    elif user_input.lower() == '退出':
                        logger.info("用户选择退出对话。")
                        print("对话已结束，清理计划未执行。")
                        return
                    else:
                        # 记录用户反馈到对话历史
                        conversation_history.append({"role": "user", "content": user_input})
                        logger.info(f"用户提供了反馈: {user_input}")
                        print("\n正在根据您的反馈调整计划...")
                else:
                    # 非交互式环境，自动确认计划
                    logger.info("非交互式环境，自动确认清理计划。")
                    print("\n非交互式环境检测到，自动确认清理计划。")
                    plan_confirmed = True
                    conversation_history.append({"role": "user", "content": "我确认这个计划可行。"})
            except EOFError:
                logger.info("在非交互式环境中无法获取用户输入，自动确认计划。")
                print("\n非交互式环境检测到，自动确认清理计划。")
                plan_confirmed = True
                conversation_history.append({"role": "user", "content": "我确认这个计划可行。"})
                
        except Exception as e:
            logger.error(f"生成清理计划时发生异常: {e}")
            print(f"错误：生成清理计划时发生异常: {e}")
            return
    
    # 用户已确认计划可行，询问是否开始执行清理
    try:
        # 检查是否在交互式环境中
        if sys.stdin.isatty():
            execute_confirm = input("\n是否开始执行清理计划？(yes/no): ").strip().lower()
            if execute_confirm != 'yes':
                logger.info("用户选择不执行清理计划。")
                print("清理计划未执行。")
                return
        else:
            # 非交互式环境，自动跳过执行（仅显示计划）
            logger.info("非交互式环境，跳过清理计划执行。")
            print("\n非交互式环境检测到，清理计划已生成但不会自动执行。")
            print("如需执行，请在交互式环境中重新运行命令。")
            return
    except EOFError:
        logger.info("在非交互式环境中无法确认执行，跳过执行。")
        print("\n非交互式环境检测到，清理计划已生成但不会自动执行。")
        print("如需执行，请在交互式环境中重新运行命令。")
        return
    
    # 开始执行清理计划
    logger.info("用户确认执行清理计划。")
    print("\n开始执行清理计划...")
    
    # 检查是否可以自动执行计划
    if task_manager and hasattr(task_manager, 'start_ai_planned_task'):
        try:
            ai_task_id = task_manager.start_ai_planned_task(user_goal=goal, current_context=context, precomputed_plan=plan)
            if ai_task_id:
                print(f"\nAI 规划的任务已启动，ID: {ai_task_id}")
                print("你可以使用 'progress --type ai' 命令来跟踪进度。")
            else:
                print("\n启动AI规划的任务失败。请检查日志。")
        except Exception as e:
            logger.error(f"执行清理计划时发生异常: {e}")
            print(f"错误：执行清理计划时发生异常: {e}")
    else:
        logger.warning("任务管理器不可用或缺少start_ai_planned_task方法，无法执行清理计划。")
        print("\n错误：当前系统配置无法自动执行清理计划。请联系开发人员。")

def run_scan(args):
    """Handles the 'scan' command."""
    logger = app_context["logger"]
    task_manager = app_context["task_manager"]
    
    if not task_manager:
        logger.error("任务管理器未初始化，无法扫描。")
        return

    logger.info("开始扫描磁盘...")
    scan_paths = args.paths.split(',') if args.paths else ["C:\\"] # Default C:\
    exclude_paths = args.exclude.split(',') if args.exclude else []
    logger.info(f"扫描路径: {scan_paths}")
    logger.info(f"排除路径: {exclude_paths}")

    try:
        scan_id = task_manager.start_scan(scan_paths=scan_paths, exclude_paths=exclude_paths)
        if not scan_id:
            logger.error("启动扫描失败。")
            return

        logger.info(f"扫描任务已启动，ID: {scan_id}")
        print("正在扫描，请稍候...")

        # Progress reporting loop (optional, depends on TaskManager implementation)
        while getattr(task_manager.scanner, '_is_scanning', False): # Check if scanning
            try:
                progress = task_manager.get_scan_progress()
                # Example progress: adjust format as needed
                progress_percent = progress.get('progress', 0) * 100
                total_items = progress.get('total_items', 0)
                total_size_gb = progress.get('total_size', 0) / (1024**3)
                sys.stdout.write(f"\r扫描进度: {progress_percent:.2f}% | 已扫描 {total_items} 项 | 总大小: {total_size_gb:.2f} GB")
                sys.stdout.flush()
            except Exception as e:
                logger.warning(f"获取扫描进度时出错: {e}")
                sys.stdout.write("\r正在扫描...") # Fallback message
                sys.stdout.flush()
            time.sleep(1) 
        
        sys.stdout.write("\n") # Newline after progress
        logger.info("扫描完成。")
        
        # Display basic results (optional)
        scan_result = task_manager.get_scan_result(scan_id)
        if scan_result:
            # Assuming scan_result is an object with attributes like total_items, total_size
            print(f"扫描ID: {scan_id}")
            if hasattr(scan_result, 'total_items'):
                 print(f"总文件数: {scan_result.total_items}")
            if hasattr(scan_result, 'total_size'):
                 print(f"总大小: {scan_result.total_size / (1024**3):.2f} GB")
            # Add more result details if needed, e.g., categories, duplicates
        else:
            logger.warning(f"无法获取扫描ID {scan_id} 的结果。")

    except KeyboardInterrupt:
        logger.warning("用户中断扫描。")
        if hasattr(task_manager, 'stop_scan'):
            task_manager.stop_scan()
        print("\n扫描已中断。")
    except Exception as e:
        logger.error(f"扫描过程中发生错误: {e}", exc_info=True)
        print(f"扫描失败，请查看日志。")

def run_clean(args):
    """Handles the 'clean' command."""
    # 实现清理命令的逻辑
    logger = app_context["logger"]
    task_manager = app_context["task_manager"]
    
    if not task_manager:
        logger.error("任务管理器未初始化，无法清理。")
        return
    
    if not args.scan_id:
        logger.error("未指定扫描ID，无法清理。")
        return
    
    logger.info(f"开始清理，基于扫描ID: {args.scan_id}")
    categories = args.categories.split(',') if args.categories else None
    create_backup = not args.no_backup
    
    try:
        task_id = task_manager.start_clean_task(
            scan_id=args.scan_id,
            categories=categories,
            create_backup=create_backup
        )
        
        if not task_id:
            logger.error("启动清理任务失败。")
            return
            
        logger.info(f"清理任务已启动，ID: {task_id}")
        print("正在清理，请稍候...")
        
        # Progress reporting loop
        while getattr(task_manager.cleaner, '_is_cleaning', False):
            try:
                progress = task_manager.get_clean_progress()
                progress_percent = progress.get('progress', 0) * 100
                cleaned_size_mb = progress.get('cleaned_size', 0) / (1024**2)
                total_size_mb = progress.get('total_size', 0) / (1024**2)
                sys.stdout.write(f"\r清理进度: {progress_percent:.2f}% | 已清理: {cleaned_size_mb:.2f} MB / {total_size_mb:.2f} MB")
                sys.stdout.flush()
            except Exception as e:
                logger.warning(f"获取清理进度时出错: {e}")
                sys.stdout.write("\r正在清理...") 
                sys.stdout.flush()
            time.sleep(1)
            
        sys.stdout.write("\n") # Newline after progress
        logger.info("清理完成。")
        
        # Display results
        clean_task = task_manager.get_clean_task(task_id)
        if clean_task:
            print(f"清理任务ID: {task_id}")
            if hasattr(clean_task, 'cleaned_size'):
                print(f"已清理空间: {clean_task.cleaned_size / (1024**2):.2f} MB")
            if hasattr(clean_task, 'backup_id') and clean_task.backup_id:
                print(f"备份ID: {clean_task.backup_id}")
        else:
            logger.warning(f"无法获取清理任务ID {task_id} 的结果。")
            
    except KeyboardInterrupt:
        logger.warning("用户中断清理。")
        if hasattr(task_manager, 'stop_clean_task'):
            task_manager.stop_clean_task()
        print("\n清理已中断。")
    except Exception as e:
        logger.error(f"清理过程中发生错误: {e}", exc_info=True)
        print(f"清理失败，请查看日志。")

def run_restore(args):
    """Handles the 'restore' command."""
    logger = app_context["logger"]
    task_manager = app_context["task_manager"]
    
    if not task_manager:
        logger.error("任务管理器未初始化，无法还原备份。")
        return
        
    if not args.backup_id:
        logger.error("未指定备份ID，无法还原。")
        return
        
    logger.info(f"开始还原备份，ID: {args.backup_id}")
    
    try:
        success = task_manager.restore_from_backup(args.backup_id)
        if success:
            logger.info("备份还原成功。")
            print("备份已成功还原。")
        else:
            logger.error("备份还原失败。")
            print("备份还原失败，请查看日志。")
    except Exception as e:
        logger.error(f"还原备份过程中发生错误: {e}", exc_info=True)
        print(f"还原备份失败，请查看日志。")

def run_list_backups(args):
    """Handles the 'list-backups' command."""
    logger = app_context["logger"]
    task_manager = app_context["task_manager"]
    
    if not task_manager:
        logger.error("任务管理器未初始化，无法列出备份。")
        return
        
    logger.info("获取备份列表...")
    
    try:
        backups = task_manager.list_backups()
        if not backups:
            print("没有找到备份。")
            return
            
        print("\n===== 备份列表 =====\n")
        for backup in backups:
            # 假设backup对象有id, timestamp, size等属性
            backup_id = backup.id if hasattr(backup, 'id') else "未知ID"
            timestamp = backup.timestamp if hasattr(backup, 'timestamp') else "未知时间"
            size = backup.size if hasattr(backup, 'size') else 0
            print(f"备份ID: {backup_id}")
            print(f"创建时间: {timestamp}")
            print(f"大小: {size / (1024**2):.2f} MB")
            print("-------------------")
    except Exception as e:
        logger.error(f"获取备份列表时发生错误: {e}", exc_info=True)
        print(f"无法获取备份列表，请查看日志。")

def run_list_duplicates(args):
    """Handles the 'list-duplicates' command."""
    logger = app_context["logger"]
    task_manager = app_context["task_manager"]
    
    if not task_manager:
        logger.error("任务管理器未初始化，无法列出重复文件。")
        return
        
    if not args.scan_id:
        logger.error("未指定扫描ID，无法列出重复文件。")
        return
        
    logger.info(f"获取扫描ID {args.scan_id} 的重复文件...")
    
    try:
        # 假设task_manager有get_duplicates方法
        duplicates = task_manager.get_duplicates(args.scan_id) if hasattr(task_manager, 'get_duplicates') else []
        if not duplicates:
            print("没有找到重复文件。")
            return
            
        print("\n===== 重复文件列表 =====\n")
        for i, duplicate_group in enumerate(duplicates, 1):
            total_size = sum(f.size for f in duplicate_group) if all(hasattr(f, 'size') for f in duplicate_group) else 0
            print(f"组 {i}: {len(duplicate_group)} 个文件，总大小: {total_size / (1024**2):.2f} MB")
            for j, file in enumerate(duplicate_group, 1):
                file_path = file.path if hasattr(file, 'path') else "未知路径"
                file_size = file.size if hasattr(file, 'size') else 0
                print(f"  {j}. {file_path} ({file_size / (1024**2):.2f} MB)")
            print("-------------------")
    except Exception as e:
        logger.error(f"获取重复文件列表时发生错误: {e}", exc_info=True)
        print(f"无法获取重复文件列表，请查看日志。")

def run_schedule(args):
    """管理自动清理计划"""
    logger = app_context["logger"]
    scheduler = app_context["scheduler"]
    config = app_context["config"]
    
    if not scheduler:
        logger.error("调度器服务未初始化，无法管理自动清理计划。")
        print("错误：调度器服务未初始化。请确保应用程序正确初始化。")
        return
    
    # 检查是否同时指定了启用和禁用参数
    if args.enable and args.disable:
        logger.error("不能同时启用和禁用自动清理。")
        print("错误：不能同时指定 --enable 和 --disable 参数。")
        return
    
    # 获取当前配置
    current_enabled = config.get("schedule.auto_clean.enabled", False)
    current_interval = config.get("schedule.auto_clean.interval_days", 14)
    current_categories = config.get("schedule.auto_clean.categories", "temp_files,cache_files")
    
    # 显示当前状态
    if not (args.enable or args.disable or args.interval is not None or args.categories):
        print("当前自动清理计划状态:")
        print(f"  启用状态: {'已启用' if current_enabled else '已禁用'}")
        print(f"  清理间隔: {current_interval} 天")
        print(f"  清理类别: {current_categories}")
        return
    
    # 更新配置
    changes_made = False
    
    # 更新启用/禁用状态
    if args.enable:
        config.set("schedule.auto_clean.enabled", True)
        changes_made = True
        print("已启用自动清理计划。")
    elif args.disable:
        config.set("schedule.auto_clean.enabled", False)
        changes_made = True
        print("已禁用自动清理计划。")
    
    # 更新清理间隔
    if args.interval is not None:
        if args.interval < 1:
            logger.error("清理间隔必须大于等于1天。")
            print("错误：清理间隔必须大于等于1天。")
            return
        config.set("schedule.auto_clean.interval_days", args.interval)
        changes_made = True
        print(f"已将清理间隔设置为 {args.interval} 天。")
    
    # 更新清理类别
    if args.categories:
        config.set("schedule.auto_clean.categories", args.categories)
        changes_made = True
        print(f"已将清理类别设置为: {args.categories}")
    
    # 如果进行了更改，重新加载调度器
    if changes_made:
        try:
            # 保存配置
            config.save_config()
            # 重新启动调度器以应用新配置
            if hasattr(scheduler, 'stop') and callable(scheduler.stop):
                scheduler.stop()
            if hasattr(scheduler, 'start') and callable(scheduler.start):
                scheduler.start()
            print("调度器配置已更新并重新加载。")
        except Exception as e:
            logger.error(f"更新调度器配置时出错: {e}")
            print(f"错误：更新调度器配置时出错: {e}")

def run_service(args):
    """Handles the 'service' command."""
    logger = app_context["logger"]
    scheduler = app_context["scheduler"]
    
    if not scheduler:
        logger.error("调度器未初始化，无法启动服务。")
        return
        
    logger.info("启动后台服务...")
    print("正在启动后台服务，按Ctrl+C停止...")
    
    try:
        # 启动调度器
        scheduler.start()
        
        # 保持服务运行，直到收到中断信号
        while True:
            time.sleep(1)
            # 可以在这里添加定期更新系统信息的代码
            if hasattr(scheduler, 'update_system_info'):
                scheduler.update_system_info()
    except KeyboardInterrupt:
        logger.info("收到用户中断，停止服务...")
        print("\n服务已停止。")
    except Exception as e:
        logger.error(f"服务运行过程中发生错误: {e}", exc_info=True)
        print(f"服务运行失败，请查看日志。")
    finally:
        # 确保调度器被正确关闭
        if hasattr(scheduler, 'close'):
            scheduler.close()

# --- GUI Command Implementation ---
def run_gui(args):
    """启动图形用户界面"""
    logger = app_context["logger"]
    
    # 目前GUI功能尚未实现，显示提示信息
    logger.info("GUI功能尚未实现，请等待后续版本更新。")
    print("图形用户界面功能尚未实现，请等待后续版本更新。")
    print("您可以继续使用命令行界面操作程序。")
    return

def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check if 'ui' argument is present to launch GUI
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'ui':
        try:
            from ui.app import App
            if not initialize_app(): # Initialize backend components if needed by UI
                print("无法初始化应用程序后端，UI可能功能不全。", file=sys.stderr)
                # Decide if UI should still launch or exit
                # For now, let's allow UI to launch with a warning
            
            ui_app = App() # Potentially pass app_context if UI needs it
            ui_app.mainloop()
        except ImportError as e:
            print(f"错误：无法启动UI界面，缺少模块: {e}", file=sys.stderr)
            print("请确保UI组件已正确安装或配置。", file=sys.stderr)
        except Exception as e:
            print(f"启动UI界面时发生未知错误: {e}", file=sys.stderr)
        finally:
            cleanup_app() # Ensure backend cleanup even if UI fails or closes
        return # Exit after UI closes

    
    # --- Main Argument Parser ---
    # If not launching UI, proceed with CLI argument parsing
    parser = argparse.ArgumentParser(description="C盘清理工具", prog="c_disk_cleaner")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # scan命令
    scan_parser = subparsers.add_parser("scan", help="扫描磁盘并分析空间使用情况")
    scan_parser.add_argument("--paths", help="要扫描的路径，用逗号分隔 (默认: C:\\)")
    scan_parser.add_argument("--exclude", help="要排除的路径，用逗号分隔")
    scan_parser.set_defaults(func=run_scan)
    
    # clean命令
    clean_parser = subparsers.add_parser("clean", help="清理磁盘空间")
    clean_parser.add_argument("--scan-id", help="要使用的扫描ID (默认: 最新的扫描)")
    clean_parser.add_argument("--categories", help="要清理的文件类别，用逗号分隔 (例如: temp,large,duplicate)")
    clean_parser.add_argument("--no-backup", action="store_true", help="不创建备份")
    clean_parser.set_defaults(func=run_clean)
    
    # restore命令
    restore_parser = subparsers.add_parser("restore", help="从备份恢复文件")
    restore_parser.add_argument("--backup-id", required=True, help="要恢复的备份ID")
    restore_parser.set_defaults(func=run_restore)
    
    # list-backups命令
    list_backups_parser = subparsers.add_parser("list-backups", help="列出可用的备份")
    list_backups_parser.set_defaults(func=run_list_backups)
    
    # list-duplicates命令
    list_duplicates_parser = subparsers.add_parser("list-duplicates", help="列出重复文件")
    list_duplicates_parser.add_argument("--scan-id", help="要使用的扫描ID (默认: 最新的扫描)")
    list_duplicates_parser.add_argument("--min-size", type=int, default=1, help="最小文件大小 (MB) (默认: 1)")
    list_duplicates_parser.add_argument("--output", help="输出结果到文件")
    list_duplicates_parser.set_defaults(func=run_list_duplicates)
    
    # ai-plan命令
    ai_plan_parser = subparsers.add_parser("ai-plan", help="使用AI生成磁盘清理计划")
    ai_plan_parser.add_argument("--model", choices=["gemini", "qwen", "wenxin"], 
                              help="要使用的AI模型 (默认: 使用第一个可用的模型)")
    ai_plan_parser.add_argument("--goal", help="清理目标描述 (默认: 清理C盘，释放磁盘空间)")
    ai_plan_parser.add_argument("--free-space", type=int, help="期望释放的空间大小 (GB)")
    ai_plan_parser.add_argument("--keep-days", type=int, default=30, help="保留多少天内的文件 (默认: 30)")
    ai_plan_parser.add_argument("--paths", help="要分析的路径，多个路径用英文逗号分隔，默认C盘根目录。")
    ai_plan_parser.add_argument("--exclude", help="排除的路径，多个路径用英文逗号分隔。")
    ai_plan_parser.set_defaults(func=run_ai_plan)
    
    # schedule命令
    schedule_parser = subparsers.add_parser("schedule", help="管理自动清理计划")
    schedule_parser.add_argument("--enable", action="store_true", help="启用自动清理")
    schedule_parser.add_argument("--disable", action="store_true", help="禁用自动清理")
    schedule_parser.add_argument("--interval", type=int, help="自动清理间隔 (天)")
    schedule_parser.add_argument("--categories", help="要清理的文件类别，用逗号分隔")
    schedule_parser.set_defaults(func=run_schedule)
    
    # gui命令
    gui_parser = subparsers.add_parser("gui", help="启动图形用户界面")
    gui_parser.set_defaults(func=run_gui)
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 初始化应用程序
    if not initialize_app():
        if MODULE_ERROR:
            print(f"错误：无法导入必要的模块: {MODULE_ERROR}", file=sys.stderr)
            print("请确保所有依赖已安装并且项目结构正确。", file=sys.stderr)
        else:
            print("应用程序初始化失败，请查看日志。", file=sys.stderr)
        return 1
    
    try:
        # 如果没有指定命令，显示帮助信息
        if not args.command:
            parser.print_help()
            return 0
            
        # 执行对应的命令处理函数
        if hasattr(args, 'func'):
            args.func(args)
        else:
            print(f"未知命令: {args.command}")
            parser.print_help()
            return 1
            
        return 0
    except Exception as e:
        logger = app_context.get("logger")
        if logger:
            logger.error(f"执行命令时发生错误: {e}", exc_info=True)
        print(f"执行命令时发生错误: {e}", file=sys.stderr)
        return 1
    finally:
        # 清理资源
        cleanup_app()

if __name__ == "__main__":
    sys.exit(main())


