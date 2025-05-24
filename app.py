#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
C盘清理工具 - 主应用程序入口
Based on README.md specifications.
"""

import argparse
import sys
import time
import signal
import atexit # Added for cleanup
import os  # Needed for potential size calculation in list-duplicates
from datetime import datetime # Added for AI Plan

# Assume these modules exist based on README.md project structure
# We'll wrap the imports in try-except to allow basic execution even if modules are missing
try:
    from config.manager import ConfigManager
    from services.logger import LoggerService
    from services.task_manager import TaskManager
    from services.scheduler import SchedulerService
    from services.ai_planner import AIPlannerService # Added for ai-plan
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

    class AIPlannerService: # Added for ai-plan
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
    "ai_planner": None, # Added for ai-plan
    "initialized": False # ADDED: Flag to track initialization
}

def initialize_app():
    """Initializes application components based on config."""
    if app_context.get("initialized"):
        # If logger is available and we want to log this, uncomment below
        # logger = app_context.get("logger")
        # if logger:
        #     logger.debug("Application already initialized. Skipping re-initialization.")
        return True # Already initialized successfully
    if MODULE_ERROR:
        # Critical import error, use basic print for all messages
        print(f"CRITICAL ERROR: Failed to import necessary modules: {MODULE_ERROR}", file=sys.stderr)
        print("Please ensure all dependencies are installed and the project structure is correct.", file=sys.stderr)
        print("Application cannot continue initialization due to missing core modules.", file=sys.stderr)
        # Attempt to create a very basic logger for this specific error if possible, otherwise, it's already printed.
        try:
            app_context["logger"] = LoggerService(None).get_logger()
            if app_context["logger"]:
                 app_context["logger"].critical(f"Failed to import necessary modules: {MODULE_ERROR}")
        except:
            pass # Ignore if even basic logger fails
        return False # Indicate critical failure

    try:
        app_context["config"] = ConfigManager()
        # Initialize logger FIRST, so other initializations can use it.
        logger_service = LoggerService(app_context["config"])
        app_context["logger"] = logger_service.get_logger()
        # Now use the initialized logger for subsequent messages
        logger = app_context["logger"]

        logger.info("配置和日志服务初始化成功。正在初始化其他组件...")

        # Initialize AIPlannerService first so it can be passed to TaskManager
        app_context["ai_planner"] = AIPlannerService(config_manager=app_context["config"], logger=app_context["logger"])
        app_context["task_manager"] = TaskManager(app_context["config"], ai_planner_service=app_context["ai_planner"])
        app_context["scheduler"] = SchedulerService(app_context["config"], app_context["task_manager"])

        logger.info("所有应用程序组件初始化成功。")
        app_context["initialized"] = True # ADDED: Set flag after successful initialization
        return True
    except Exception as e:
        # Determine if logger was initialized before the exception
        current_logger = app_context.get("logger")
        error_message = f"应用程序初始化过程中发生错误: {e}"
        app_context["initialized"] = False # Ensure flag is false on error
        
        if current_logger:
            current_logger.critical(error_message, exc_info=True) # Log with stack trace
        else:
            # Logger itself failed or error occurred before logger init
            print(f"CRITICAL INIT ERROR (logger unavailable): {error_message}", file=sys.stderr)
            # Optionally print stack trace manually if needed for debugging early init failures
            import traceback
            traceback.print_exc(file=sys.stderr)
            
        print("应用程序初始化失败，请查看上述错误或日志。", file=sys.stderr) # General message to stderr
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
    # cleanup_app() will be called by atexit on sys.exit()
    sys.exit(0)

# --- Helper function to check app components ---
def check_app_component(component_name, logger_ref, is_logger_check=False):
    """Checks if a component in app_context is initialized and prints/logs error if not."""
    component = app_context.get(component_name)
    if not component:
        error_msg = f"错误：应用程序组件 '{component_name}' 未初始化。无法继续执行命令。"
        if is_logger_check:
            # If checking for logger itself and it's missing, can only print
            print(error_msg, file=sys.stderr)
        elif logger_ref:
            logger_ref.error(error_msg)
            print(error_msg, file=sys.stderr)
        else:
            # Fallback if logger_ref is also None (e.g. logger itself failed)
            print(f"(Logger not available) {error_msg}", file=sys.stderr)
        return None
    return component

# --- Command Implementations ---

def run_scan(args):
    """Handles the 'scan' command."""
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger: return

    task_manager = check_app_component("task_manager", logger)
    if not task_manager: return

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
        logger.info(f"扫描任务已启动，扫描ID: {scan_id}")
        print("正在扫描，请稍候...")

        # Progress reporting loop (optional, depends on TaskManager implementation)
        last_percent = -1
        last_print_time = 0
        while task_manager.is_scan_active(): # Check if scanning
            try:
                progress = task_manager.get_scan_progress()
                progress_percent = progress.get('progress', 0) * 100
                total_items = progress.get('total_items', 0)
                total_size_gb = progress.get('total_size', 0) / (1024**3)
                now = time.time()
                # 只在进度有明显变化或每隔2秒刷新一次
                if int(progress_percent) != last_percent or now - last_print_time > 2:
                    sys.stdout.write(f"\r扫描进度: {progress_percent:.2f}% | 已扫描 {total_items} 项 | 总大小: {total_size_gb:.2f} GB")
                    sys.stdout.flush()
                    last_percent = int(progress_percent)
                    last_print_time = now
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
            # 新增：打印所有可清理项的ID汇总
            cleanable_ids = []
            if hasattr(scan_result, 'items') and scan_result.items:
                for item in scan_result.items:
                    # 假设每个item有is_cleanable和id属性
                    if getattr(item, 'is_cleanable', False) and hasattr(item, 'id'):
                        cleanable_ids.append(str(item.id))
            if cleanable_ids:
                print("本次扫描所有可清理的ID如下：")
                print(", ".join(cleanable_ids))
            else:
                print("本次扫描未发现可清理项。")
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
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger:
        print("Logger 未初始化，无法执行清理命令。", file=sys.stderr)
        return
    task_manager = check_app_component("task_manager", logger)
    if not task_manager:
        return
    scan_id = args.scan_id
    categories = args.categories.split(',') if args.categories else []
    create_backup = args.backup
    logger.info(f"清理任务参数: scan_id={scan_id}, categories={categories}, create_backup={create_backup}")
    try:
        clean_task_id = task_manager.start_clean_task(scan_id=scan_id, categories=categories, create_backup=create_backup)
        if not clean_task_id:
            logger.error("启动清理任务失败。")
            return
        logger.info(f"清理任务已启动，ID: {clean_task_id}")
        print("正在清理，请稍候...")
        while task_manager.is_clean_active():
            try:
                progress = task_manager.get_clean_progress()
                progress_percent = progress.get('progress', 0) * 100
                cleaned_size = progress.get('cleaned_size', 0) / (1024**3)
                total_size = progress.get('total_size', 0) / (1024**3)
                sys.stdout.write(f"\r清理进度: {progress_percent:.2f}% | 已清理 {cleaned_size:.2f} GB / {total_size:.2f} GB")
                sys.stdout.flush()
            except Exception as e:
                logger.warning(f"获取清理进度时出错: {e}")
                sys.stdout.write("\r正在清理...")
                sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\n")
        logger.info("清理完成。")
        clean_task = task_manager.get_clean_task(clean_task_id)
        if clean_task:
            print(f"清理任务ID: {clean_task_id}")
            if hasattr(clean_task, 'cleaned_size'):
                print(f"已清理大小: {getattr(clean_task, 'cleaned_size', 0) / (1024**3):.2f} GB")
            if hasattr(clean_task, 'backup_id') and getattr(clean_task, 'backup_id', None):
                print(f"备份ID: {getattr(clean_task, 'backup_id', '')}")
        else:
            logger.warning(f"无法获取清理任务ID {clean_task_id} 的结果。")
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
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger:
        return

    task_manager = check_app_component("task_manager", logger)
    if not task_manager:
        return

    if not args.backup_id:
        logger.error("未指定备份ID，无法还原。")
        print("错误：未指定备份ID。请使用 --backup-id <ID> 指定要还原的备份。")
        return

    logger.info(f"开始还原备份，ID: {args.backup_id}")
    print(f"正在尝试从备份 {args.backup_id} 还原...")

    try:
        success = task_manager.restore_from_backup(args.backup_id)
        if success:
            logger.info(f"备份 {args.backup_id} 还原成功。")
            print(f"备份 {args.backup_id} 已成功还原。")
        else:
            logger.error(f"备份 {args.backup_id} 还原失败。任务管理器返回失败。")
            print(f"备份 {args.backup_id} 还原失败。请检查日志以获取更多详细信息。")
    except Exception as e:
        logger.error(f"还原备份 {args.backup_id} 过程中发生错误: {e}", exc_info=True)
        print(f"还原备份 {args.backup_id} 失败，发生意外错误。请查看日志。")

def run_list_backups(args):
    """Handles the 'list-backups' command."""
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger:
        return

    task_manager = check_app_component("task_manager", logger)
    if not task_manager:
        return

    logger.info("正在列出所有备份...")
    try:
        backups = task_manager.list_backups()
        if not backups:
            print("未找到任何备份。")
            logger.info("未找到任何备份记录。")
            return

        print("可用的备份：")
        for backup_info in backups:
            # Assuming backup_info is a dictionary or an object with attributes
            # Adjust the formatting based on what task_manager.list_backups() returns
            backup_id = getattr(backup_info, 'id', backup_info.get('id', 'N/A'))
            timestamp = getattr(backup_info, 'timestamp', backup_info.get('timestamp', 'N/A'))
            size = getattr(backup_info, 'size', backup_info.get('size', 'N/A'))
            # Convert size to a readable format if it's in bytes
            if isinstance(size, (int, float)):
                size_gb = size / (1024**3)
                size_str = f"{size_gb:.2f} GB"
            else:
                size_str = str(size)
            print(f"  - ID: {backup_id}, 时间: {timestamp}, 大小: {size_str}")
        logger.info(f"成功列出 {len(backups)} 个备份。")
    except Exception as e:
        logger.error(f"列出备份时发生错误: {e}", exc_info=True)
        print("列出备份失败，请查看日志。")

def run_progress(args):
    """Handles the 'progress' command."""
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger:
        return

    task_manager = check_app_component("task_manager", logger)
    if not task_manager:
        return

    progress_type = args.type
    logger.info(f"正在获取 {progress_type} 任务的进度...")

    try:
        if progress_type == 'scan':
            if not task_manager.is_scan_active():
                print("当前没有正在进行的扫描任务。")
                logger.info("请求扫描进度，但没有活动扫描任务。")
                return
            progress = task_manager.get_scan_progress()
            progress_percent = progress.get('progress', 0) * 100
            total_items = progress.get('total_items', 0)
            total_size_gb = progress.get('total_size', 0) / (1024**3)
            print(f"扫描进度: {progress_percent:.2f}% | 已扫描 {total_items} 项 | 总大小: {total_size_gb:.2f} GB")
            logger.info(f"扫描进度: {progress_percent:.2f}%, 项目: {total_items}, 大小: {total_size_gb:.2f} GB")
        elif progress_type == 'clean':
            if not task_manager.is_clean_active():
                print("当前没有正在进行的清理任务。")
                logger.info("请求清理进度，但没有活动清理任务。")
                return
            progress = task_manager.get_clean_progress()
            progress_percent = progress.get('progress', 0) * 100
            cleaned_size_gb = progress.get('cleaned_size', 0) / (1024**3)
            total_size_gb = progress.get('total_size', 0) / (1024**3)
            print(f"清理进度: {progress_percent:.2f}% | 已清理 {cleaned_size_gb:.2f} GB / {total_size_gb:.2f} GB")
            logger.info(f"清理进度: {progress_percent:.2f}%, 已清理: {cleaned_size_gb:.2f}GB, 总计: {total_size_gb:.2f}GB")
        else:
            # This case should ideally not be reached due to argparse choices
            logger.error(f"无效的进度类型: {progress_type}")
            print(f"错误：无效的进度类型 '{progress_type}'。请使用 'scan' 或 'clean'。")

    except Exception as e:
        logger.error(f"获取 {progress_type} 进度时发生错误: {e}", exc_info=True)
        print(f"获取 {progress_type} 进度失败，请查看日志。")

def run_list_duplicates(args):
    """Handles the 'list-duplicates' command."""
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger:
        return

    task_manager = check_app_component("task_manager", logger)
    if not task_manager:
        return

    scan_id = args.scan_id
    logger.info(f"正在列出扫描ID {scan_id} 中的重复文件...")
    print(f"正在查找扫描ID {scan_id} 中的重复文件...")

    try:
        # Assuming TaskManager has a method like get_duplicate_files(scan_id)
        # This method should return a list of groups of duplicate files.
        # Example: [[fileA_path1, fileA_path2], [fileB_path1, fileB_path2, fileB_path3]]
        if not hasattr(task_manager, 'get_duplicate_files'):
            logger.error("TaskManager 中缺少 'get_duplicate_files' 方法。无法列出重复文件。")
            print("错误：此功能当前不可用。")
            return

        duplicate_groups = task_manager.get_duplicate_files(scan_id)

        if not duplicate_groups:
            print(f"在扫描ID {scan_id} 中未找到重复文件。")
            logger.info(f"在扫描ID {scan_id} 中未找到重复文件。")
            return

        print(f"扫描ID {scan_id} 中的重复文件组：")
        group_count = 0
        total_duplicates = 0
        for i, group in enumerate(duplicate_groups):
            if len(group) > 1:
                group_count += 1
                print(f"  组 {group_count}: (共 {len(group)} 个文件)")
                # Calculate size of one file in the group (assuming they are identical)
                # This might require TaskManager to provide size info or an additional call
                # For simplicity, we'll just list paths here.
                # If size is available, e.g., from a more detailed duplicate_info object:
                # first_file_path = group[0]
                # file_size = os.path.getsize(first_file_path) # This is a basic way, TM might have better
                # print(f"    大小 (单个文件): {file_size / (1024*1024):.2f} MB")
                for file_path in group:
                    print(f"    - {file_path}")
                    total_duplicates +=1
        
        if group_count == 0:
            print(f"在扫描ID {scan_id} 中未找到重复文件组 (每组至少2个文件)。")
            logger.info(f"在扫描ID {scan_id} 中未找到实际的重复文件组。")
        else:
            logger.info(f"成功列出 {group_count} 组重复文件，共 {total_duplicates} 个重复文件条目，来自扫描ID {scan_id}。")

    except FileNotFoundError as e:
        logger.error(f"列出重复文件时发生文件未找到错误 (扫描ID: {scan_id}): {e}")
        print(f"错误：找不到与扫描ID {scan_id} 相关的数据或文件。它可能已被删除或损坏。")
    except Exception as e:
        logger.error(f"列出扫描ID {scan_id} 的重复文件时发生错误: {e}", exc_info=True)
        print(f"列出重复文件失败 (扫描ID: {scan_id})。请查看日志。")

# --- AI Plan Command Implementation ---
def run_ai_plan(args):
    """使用AI模型生成磁盘清理计划"""
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger: return

    ai_planner = check_app_component("ai_planner", logger)
    if not ai_planner:
        print("错误：AI规划服务未初始化或初始化失败。可能原因：")
        print("1. 配置文件 (例如 config/default.yaml) 中缺少AI相关的API密钥设置 (例如 ai.gemini_api_key)。")
        print("2. AI规划服务在应用程序启动时遇到初始化问题。")
        print("请检查应用程序日志和配置文件以获取详细信息。")
        print("如果使用的是Gemini模型，可以尝试运行 'python utils/test_api_key.py' (如果存在) 来测试API密钥。")
        return

    available_models = []
    if hasattr(ai_planner, 'get_available_models'):
        try:
            available_models = ai_planner.get_available_models()
        except Exception as e:
            logger.error(f"获取可用AI模型列表失败: {e}")
            print(f"警告: 获取可用AI模型列表失败: {e}")
    
    if not available_models:
        logger.warning("AI规划器未报告任何可用模型。将尝试使用默认或第一个配置的模型。")

    current_model_display = "默认"
    if hasattr(ai_planner, 'current_model') and ai_planner.current_model:
        current_model_display = ai_planner.current_model
    elif available_models:
        current_model_display = available_models[0]

    if hasattr(args, 'model') and args.model:
        if available_models and args.model not in available_models:
            logger.warning(f"指定的模型 '{args.model}' 不在AI规划器报告的可用模型列表中: {', '.join(available_models)}. 仍会尝试使用。")
            print(f"警告：指定的模型 '{args.model}' 可能不受当前AI规划器支持。可用: {', '.join(available_models) if available_models else '无明确列表'}")
            print(f"将尝试使用模型 '{args.model}'。")
            current_model_display = args.model
        elif hasattr(ai_planner, 'set_model'):
            try:
                success = ai_planner.set_model(args.model)
                if success:
                    current_model_display = args.model
                    logger.info(f"已成功切换到AI模型: {args.model}")
                else:
                    logger.warning(f"切换到模型 '{args.model}' 失败 (set_model返回False)。将使用 '{current_model_display}' 模型。")
                    print(f"警告：切换到模型 '{args.model}' 失败。将使用 '{current_model_display}' 模型。")
            except Exception as e:
                logger.error(f"切换到模型 '{args.model}' 时发生错误: {e}")
                print(f"警告：切换到模型 '{args.model}' 时出错。将使用 '{current_model_display}' 模型。")
        else:
             current_model_display = args.model
             logger.info(f"用户指定模型 '{args.model}'。AI规划器将尝试使用它。")

    print(f"\n使用 {current_model_display.capitalize()} 模型生成清理计划...\n")
    
    goal = args.goal if hasattr(args, 'goal') and args.goal else "清理C盘，释放磁盘空间，重点关注临时文件、大文件和重复文件。"
    
    default_scan_paths = ["C:\\"] # Corrected
    if app_context.get("config"):
        default_scan_paths = app_context["config"].get("scanner.default_scan_paths", ["C:\\"]) # Corrected

    scan_paths = args.paths.split(',') if hasattr(args, 'paths') and args.paths else default_scan_paths
    exclude_paths = args.exclude.split(',') if hasattr(args, 'exclude') and args.exclude else (app_context["config"].get("scanner.default_exclude_paths", []) if app_context.get("config") else []) # Corrected
    
    logger.info(f"AI规划目标: {goal}")
    logger.info(f"AI分析路径: {scan_paths}")
    logger.info(f"AI排除路径: {exclude_paths}")
    
    context = {
        "system_info": {
            "os": sys.platform,
            "free_disk_space_gb": args.free_space if hasattr(args, 'free_space') and args.free_space is not None else None
        },
        "user_preferences": {
            "keep_files_newer_than_days": args.keep_days if hasattr(args, 'keep_days') and args.keep_days is not None else None
        },
        "scan_paths": scan_paths,
        "exclude_paths": exclude_paths,
        "current_datetime": datetime.now().isoformat()
    }
    
    logger.debug(f"为AI规划器准备的上下文: {context}")
    
    try:
        sys.stdout.write("AI正在思考中，请稍候...")
        sys.stdout.flush()
        
        plan = ai_planner.generate_plan(user_goal=goal, current_context=context)
        
        sys.stdout.write("\r" + " " * 30 + "\r") 
        sys.stdout.flush()

        if plan and isinstance(plan, dict) and plan.get("steps"):
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

            # 检查并打印AI的思考过程
            if "thinking_process" in plan:
                print("\nAI的思考过程:")
                # 假设thinking_process是一个字符串或列表，这里简单打印
                process = plan["thinking_process"]
                if isinstance(process, list):
                    for step in process:
                        print(f"- {step}")
                else:
                    print(process)

            # 检查是否可以自动执行计划 (如果Task Manager支持)
            
            task_manager = check_app_component("task_manager", logger)
            if task_manager and hasattr(task_manager, 'start_ai_planned_task'):
                confirm_execution = ""
                try:
                    confirm_execution = input("\n是否要执行此计划? (yes/no): ").strip().lower()
                except EOFError:
                    logger.warning("在非交互式环境中无法确认执行AI计划，默认不执行。")
                    confirm_execution = "no"

                if confirm_execution == 'yes':
                    logger.info("用户确认执行AI生成的计划。")
                    print("正在尝试执行计划...")
                    ai_task_id = task_manager.start_ai_planned_task(user_goal=goal, current_context=context, precomputed_plan=plan)
                    if ai_task_id:
                        print(f"\nAI 规划的任务已启动，ID: {ai_task_id}")
                        print("你可以使用 'progress --type ai' (如果已实现) 或查看日志来跟踪进度。")
                    else:
                        print("\n启动AI规划的任务失败。请检查日志。")
                else:
                    logger.info("用户选择不执行AI生成的计划或无法确认。")
                    print("计划未执行。")
            else:
                logger.info("任务管理器不可用或缺少 'start_ai_planned_task' 方法。计划仅供查看。")
                print("\n注意: 当前配置无法自动执行此计划。计划仅供查看。")

        elif plan and isinstance(plan, dict) and "error" in plan:
            logger.error(f"AI规划器返回错误: {plan['error']}")
            print(f"错误：AI规划器无法生成计划: {plan['error']}")
            if "API key" in plan.get("error", ""):
                 print("请检查您的AI服务API密钥是否正确配置并且有效。")
        elif plan is None:
            logger.error("AI规划器返回了None，表示规划失败或未生成计划。")
            print("错误：AI规划器未能生成计划 (返回None)。请检查日志以获取详细信息。")
        else:
            logger.warning(f"AI规划器未能生成有效的计划或返回了意外的格式: {plan}")
            print("错误：AI规划器未能生成有效的计划或返回格式无法识别。")
            print("请检查日志以获取更多信息。如果问题持续，请尝试不同的目标或模型。")

    except KeyboardInterrupt:
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()
        logger.warning("用户中断了AI计划生成。")
        print("\nAI计划生成已由用户中断。")
    except Exception as e:
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()
        logger.error(f"运行AI计划时发生错误: {e}", exc_info=True)
        print(f"错误：生成AI计划时发生意外错误: {e}")
        print("请检查日志以获取详细信息。")

    except Exception as e:
        logger.error(f"生成清理计划时发生异常: {e}", exc_info=True)
        print(f"错误：生成清理计划时发生异常: {e}")
        # Optionally, attempt fallback to other models if primary fails, similar to original logic if desired.

def run_service(args):
    """Handles the 'service' command to run in background mode."""
    logger = check_app_component("logger", None, is_logger_check=True)
    if not logger:
        sys.exit(1) # Critical, cannot run service without logger

    scheduler = check_app_component("scheduler", logger)
    if not scheduler:
        sys.exit(1) # Critical, cannot run service without scheduler

    logger.info("以服务模式启动应用程序...")
    print("应用程序正在后台服务模式下运行。按 Ctrl+C 停止。")
    
    try:
        scheduler.start() # This should block or run in a separate thread
        # Keep the main thread alive if scheduler.start() is non-blocking
        # and doesn't have its own keep-alive mechanism.
        # For a simple console service, scheduler.start() might be blocking.
        # If it's a true daemon, this part might be different (e.g. using a library like python-daemon)
        while True:
            # Periodically update system info if scheduler doesn't do it internally
            if hasattr(scheduler, 'update_system_info'):
                 scheduler.update_system_info()
            time.sleep(60)  # Keep alive, adjust interval as needed
    except KeyboardInterrupt:
        logger.info("收到用户中断信号 (Ctrl+C)，正在停止服务...")
        print("\n正在停止服务...")
    except Exception as e:
        logger.error(f"服务模式运行时发生意外错误: {e}", exc_info=True)
        print(f"服务因错误停止。请查看日志。")
    finally:
        # Cleanup is handled by atexit, but explicit stop for scheduler might be good here
        if hasattr(scheduler, 'close'):
            try:
                scheduler.close()
                logger.info("调度服务已在服务模式退出时关闭。")
            except Exception as e:
                logger.error(f"关闭调度服务时出错: {e}")
        logger.info("服务模式已停止。")
        print("服务已停止。")



def main():
    # 首先初始化应用程序，以便日志记录器可用于后续操作
    if not initialize_app():
        sys.exit(1)

    # 初始化后获取日志记录器实例
    logger = app_context.get("logger")

    parser = argparse.ArgumentParser(description='C盘清理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令', required=False) # 'required=False' to handle no command case gracefully

    # 扫描命令
    scan_parser = subparsers.add_parser('scan', help='扫描磁盘')
    scan_parser.add_argument('--paths', type=str, help='要扫描的路径，多个路径用逗号分隔')
    scan_parser.add_argument('--exclude', type=str, help='排除的路径，多个路径用逗号分隔')
    scan_parser.set_defaults(func=run_scan)

    # 清理命令
    clean_parser = subparsers.add_parser('clean', help='清理磁盘')
    clean_parser.add_argument('--scan-id', type=str, required=True, help='要清理的扫描ID')
    clean_parser.add_argument('--categories', type=str, help='要清理的类别，多个类别用逗号分隔')
    clean_parser.add_argument('--backup', action='store_true', help='清理前是否创建备份')
    clean_parser.set_defaults(func=run_clean)

    # 还原命令
    restore_parser = subparsers.add_parser('restore', help='从备份还原')
    restore_parser.add_argument('--backup-id', type=str, required=True, help='备份ID')
    restore_parser.set_defaults(func=run_restore)

    # 备份列表命令
    backups_parser = subparsers.add_parser('list-backups', help='列出所有备份')
    backups_parser.set_defaults(func=run_list_backups)

    # 进度命令
    progress_parser = subparsers.add_parser('progress', help='查看当前任务进度')
    progress_parser.add_argument('--type', type=str, choices=['scan', 'clean'], required=True, help='进度类型')
    progress_parser.set_defaults(func=run_progress)

    # 列出重复文件命令
    list_duplicates_parser = subparsers.add_parser("list-duplicates", help="列出指定扫描中的重复文件")
    list_duplicates_parser.add_argument("--scan-id", required=True, help="要查找重复文件的扫描ID")
    list_duplicates_parser.add_argument('--min-size', type=int, default=1024*1024, help='重复文件的最小大小 (字节), 默认1MB')
    list_duplicates_parser.set_defaults(func=run_list_duplicates)

    # 服务命令
    service_parser = subparsers.add_parser("service", help="以持续运行的后台服务模式启动")
    service_parser.set_defaults(func=run_service)
    
    # AI规划命令
    ai_plan_parser = subparsers.add_parser("ai-plan", help="使用AI生成磁盘清理计划")
    ai_plan_parser.add_argument("--model", type=str, choices=["gemini", "qwen", "wenxin"], 
                              help="要使用的AI模型 (默认: 使用第一个可用的模型)")
    ai_plan_parser.add_argument("--goal", type=str, default="清理C盘，释放磁盘空间，重点关注临时文件、大文件和重复文件。", help="清理目标描述 (默认: 清理C盘，释放磁盘空间)")
    ai_plan_parser.add_argument("--free-space", type=int, help="期望释放的空间大小 (GB)")
    ai_plan_parser.add_argument("--keep-days", type=int, default=30, help="保留多少天内的文件 (默认: 30)")
    ai_plan_parser.add_argument("--paths", help="要分析的路径，多个路径用英文逗号分隔，默认C盘根目录。")
    ai_plan_parser.add_argument("--exclude", help="排除的路径，多个路径用英文逗号分隔。")
    ai_plan_parser.set_defaults(func=run_ai_plan)
    args = parser.parse_args() # Ensure this is after all subparsers are added
    if not initialize_app():
        sys.exit(1) # Exit if initialization fails
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup_app)

    # 如果没有提供任何命令，则打印帮助信息并退出
    if len(sys.argv) == 1:
        print("\n欢迎使用C盘清理工具！\n")
        parser.print_help()
        print("\n示例用法：")
        print("  python app.py scan --paths C:\\,D:\\ --exclude C:\\Windows")
        print("  python app.py clean --scan-id <SCAN_ID> --categories 临时文件,日志 --backup")
        print("  python app.py restore --backup-id <BACKUP_ID>")
        print("  python app.py list-backups")
        print("  python app.py list-duplicates --scan-id <SCAN_ID>")
        print("  python app.py progress --type scan")
        print("  python app.py service")
        sys.exit(0)

    try:
        args = parser.parse_args()
        if logger:
            logger.info(f"执行命令: {args.command}，参数: {vars(args)}")
        
        if hasattr(args, 'func') and args.func is not None:
            if logger:
                logger.info(f"准备分发到处理函数: {args.func.__name__} (命令: '{args.command}')")
            args.func(args)
        elif args.command:
             if logger: logger.error(f"未知或未处理的命令: {args.command}")
             parser.print_help()
             sys.exit(1)
        else:
            # Should be caught by len(sys.argv) == 1, but as a fallback:
            parser.print_help()
            sys.exit(0)

    except argparse.ArgumentError as e:
        if logger:
            logger.error(f"命令行参数错误: {e}")
        print(f"参数错误: {e}", file=sys.stderr)
        # Attempt to print help for the specific sub-command if possible
        # This is a bit tricky as 'e' doesn't directly give subparser name
        # For now, print general help.
        parser.print_help(file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        command_name = "未知"
        # Check if args is defined and has command attribute
        # args might not be defined if parsing failed very early
        parsed_args = None
        try: parsed_args = parser.parse_known_args()[0] # Try to get command if possible
        except: pass
        if parsed_args and hasattr(parsed_args, 'command'):
            command_name = parsed_args.command
        
        if logger:
            logger.error(f"执行命令 '{command_name}' 时发生意外错误: {e}", exc_info=True)
        else:
            print(f"执行命令 '{command_name}' 时发生意外错误: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

        if MODULE_ERROR:
            print(f"另外，检测到初始模块加载错误: {MODULE_ERROR}", file=sys.stderr)
            print("请确保所有依赖已安装并且项目结构正确。", file=sys.stderr)
        
        print(f"程序因意外错误终止。请检查日志获取详细信息。", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # atexit 已在文件顶部导入并注册
    main()

