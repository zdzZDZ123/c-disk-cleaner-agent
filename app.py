#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
C盘清理工具 - 主应用程序入口
Based on README.md specifications.
支持多种AI模型（Gemini、Qwen）生成清理计划
"""

import argparse
import sys
import time
import signal
import os  # Needed for potential size calculation in list-duplicates
from pathlib import Path
import psutil
import yaml
import json
from datetime import datetime

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
    # 使用实际的类导入，而不是虚拟类定义
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
        # LoggerService needs log file path, not config
        logger_service = LoggerService("logs/app.log") 
        app_context["logger"] = logger_service 
        
        # Assuming TaskManager needs config (and potentially a DB instance implicitly)
        app_context["task_manager"] = TaskManager(app_context["config"]) 
        
        # Assuming SchedulerService needs config and task_manager
        app_context["scheduler"] = SchedulerService(app_context["config"], app_context["task_manager"])
        
        # Initialize AI Planner Service
        app_context["ai_planner"] = AIPlannerService(app_context["config"])
        
        app_context["logger"].info("应用程序组件初始化成功。")
        return True
    except Exception as e:
        print(f"应用程序初始化失败: {e}", file=sys.stderr)
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

def discover_junk_dirs():
    from pathlib import Path
    user = Path.home()
    dirs = [
        # 浏览器缓存
        user / 'AppData/Local/Google/Chrome/User Data/Default/Cache',
        user / 'AppData/Local/Microsoft/Edge/User Data/Default/Cache',
        user / 'AppData/Local/Mozilla/Firefox/Profiles',
        # IM 软件缓存
        user / 'AppData/Local/Tencent/QQ/Temp',
        user / 'AppData/Local/Tencent/WeChat/WeChat Files',
        user / 'AppData/Local/DingTalk',
        user / 'AppData/Local/Feishu',
        user / 'AppData/Local/WeCom',
        # 下载器缓存
        user / 'AppData/Roaming/Thunder/Temp',
        user / 'AppData/Local/IDM/Temp',
        # 播放器缓存
        user / 'AppData/Roaming/PotPlayerMini64/Cache',
        user / 'AppData/Roaming/QQPlayer/Cache',
        # 游戏启动器
        user / 'AppData/Local/Steam/htmlcache',
        user / 'AppData/Local/WeGame/Cache',
        # Office/Adobe/AutoCAD 临时文件
        user / 'AppData/Local/Microsoft/Office/UnsavedFiles',
        user / 'AppData/Local/Adobe',
        user / 'AppData/Local/Autodesk',
        # 日志
        Path('C:/Windows/Logs'),
        Path('C:/Windows/System32/LogFiles'),
        user / 'AppData/Local/Temp',
        # 缩略图缓存
        user / 'AppData/Local/Microsoft/Windows/Explorer',
        # 系统转储
        Path('C:/Windows/Minidump'),
        Path('C:/Windows/MEMORY.DMP'),
        # 驱动残留
        Path('C:/Windows/System32/DriverStore/FileRepository'),
        # Windows 更新残留
        Path('C:/Windows/SoftwareDistribution/Download'),
        Path('C:/Windows/WinSxS/Backup'),
        # 回收站
        Path('C:/$Recycle.Bin'),
        # 其他
        Path('C:/Windows/Temp'),
        user / 'Desktop',
        user / 'Downloads',
    ]
    # 展开 Firefox profiles 缓存
    firefox_profiles = list((user / 'AppData/Local/Mozilla/Firefox/Profiles').glob('*'))
    cache_dirs = [p / 'cache2' for p in firefox_profiles if (p / 'cache2').exists()]
    all_dirs = [str(d) for d in dirs if d.exists()] + [str(d) for d in cache_dirs]
    return all_dirs

def find_large_files(base_dirs, min_size_mb=500):
    from pathlib import Path
    import time
    large_files = []
    for base in base_dirs:
        base = Path(base)
        if base.exists():
            for f in base.rglob('*'):
                try:
                    if f.is_file() and f.stat().st_size > min_size_mb * 1024 * 1024:
                        large_files.append({
                            'path': str(f),
                            'size_mb': f.stat().st_size / (1024*1024),
                            'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(f.stat().st_mtime)),
                            'ext': f.suffix.lower()
                        })
                except (OSError, PermissionError) as e:
                    logger.debug(f"无法访问文件 {f}: {e}")
                    continue
    return large_files

def is_user_agree(text):
    """判断用户是否同意清理计划"""
    agree_keywords = [
        '同意清理', '确认', '可以执行', '同意', '执行', '开始清理',
        'yes', 'ok', 'go', 'accept', 'approve', 'clean', 'proceed', '继续', '没问题', '可以', '好', '行'
    ]
    text = text.strip().lower()
    return any(k in text for k in agree_keywords)

def is_cleaning_related(text):
    """判断用户输入是否与清理计划相关"""
    cleaning_keywords = [
        '清理', '删除', '移除', '计划', '路径', '文件', '目录', '文件夹', '磁盘', '空间',
        '临时', '缓存', '垃圾', '大文件', '重复', '安全', '确认', '禁止', '修改',
        'clean', 'delete', 'remove', 'plan', 'path', 'file', 'folder', 'disk', 'space',
        'temp', 'cache', 'junk', 'large', 'duplicate', 'safe', 'confirm', 'forbid', 'modify',
        '不要删除', '保留', '跳过', '排除', '增加', '减少', '调整'
    ]
    text = text.strip().lower()
    return any(k in text for k in cleaning_keywords)

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def save_conversation_history(history, filename="data/conversation_history.json"):
    ensure_dir(os.path.dirname(filename))
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_conversation_history(filename="data/conversation_history.json"):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def clear_conversation_history(filename="data/conversation_history.json"):
    if os.path.exists(filename):
        os.remove(filename)

def save_code_block(code, lang="py"):
    ensure_dir("data/ai_code")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = lang if lang else "txt"
    filename = f"data/ai_code/ai_code_{timestamp}.{ext}"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    return filename

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
    
    # 列举所有可用的主模型
    available_models = ai_planner.get_available_models()
    if not available_models:
        logger.error("未找到任何可用的AI模型。")
        print("错误：未找到任何可用的AI模型。请确保至少配置了一个有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    print("\n可用的AI主模型:")
    for m in available_models:
        print(f"  - {m}")
    # 列举每个主模型下的具体大模型（如 qwen-turbo、gemini-pro 等）
    # 这里假设 ai_planner 有 get_model_variants 方法，否则用硬编码
    model_variants = {
        "qwen": ["qwen-turbo (推荐/免费)", "qwen-plus", "qwen-max"],
        "gemini": ["gemini-pro (推荐/免费)", "gemini-1.5-pro", "gemini-1.5-flash"]
    }
    print("\n每个主模型下可用的具体大模型:")
    for m in available_models:
        print(f"  {m}: {', '.join(model_variants.get(m, ['未知']))}")
    # 友好提示
    print("\n如需指定具体大模型，可用 --model-name 参数，例如: --model-name qwen-turbo 或 --model-name gemini-1.5-pro")
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
    # 处理具体大模型参数
    model_name = getattr(args, 'model_name', None)
    if model_name:
        print(f"\n将使用您指定的具体大模型: {model_name}")
        logger.info(f"用户指定具体大模型: {model_name}")
    else:
        # 默认用推荐免费模型
        default_variant = "qwen-turbo" if ai_planner.current_model == "qwen" else "gemini-pro"
        print(f"\n未指定具体大模型，默认使用推荐免费模型: {default_variant}")
        model_name = default_variant
    print(f"\n使用 {ai_planner.current_model.capitalize()} 的 {model_name} 生成清理计划...\n")
    # 获取用户目标
    goal = args.goal if hasattr(args, 'goal') and args.goal else "清理C盘，释放磁盘空间，重点关注临时文件、大文件和重复文件。"
    # 获取扫描路径和排除路径
    if hasattr(args, 'paths') and args.paths:
        scan_paths = args.paths.split(',')
        logger.info(f"用户指定分析路径: {scan_paths}")
    else:
        scan_paths = discover_cleanup_dirs()
        if not scan_paths:
            # 动态获取系统盘符
            import os
            system_drive = os.environ.get('SystemDrive', 'C:') + os.sep
            scan_paths = [system_drive]
        logger.info(f"自动发现分析路径: {scan_paths}")
    exclude_paths = args.exclude.split(',') if hasattr(args, 'exclude') and args.exclude else []
    logger.info(f"排除路径: {exclude_paths}")
    # ==== 新增：发现更细致垃圾目录和大文件 ====
    junk_dirs = discover_junk_dirs()
    logger.info(f"发现的垃圾目录: {junk_dirs}")
    large_file_bases = list(set(scan_paths + junk_dirs + [str(Path.home() / 'Downloads'), str(Path.home() / 'Desktop')]))
    large_files = find_large_files(large_file_bases, min_size_mb=500)
    logger.info(f"发现的大文件（建议人工确认）: {large_files[:5]} ... 共{len(large_files)}个")
    # 只提取大文件路径
    large_file_paths = [f['path'] for f in large_files if 'path' in f]
    # 组装 scan_result 结构（不再调用 quick_scan，重复/模糊图片先置空）
    scan_result = {
        'garbage_dirs': junk_dirs,
        'large_files': large_file_paths,
        'duplicate_images': [],
        'blurry_images': []
    }
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
        "model_name": model_name,
        "scan_result": scan_result
    }
    
    # 生成计划循环，直到用户确认计划可行
    plan = None
    plan_confirmed = False
    # ==== 多轮上下文记忆持久化 ====
    history_file = "data/conversation_history.json"
    conversation_history = load_conversation_history(history_file)
    # ==== 角色预设 ====
    role_presets = {
        "默认": "你是一个磁盘清理智能助手，也能像ChatGPT一样回答各种问题。",
        "极客助手": "你是极客风格的技术专家，善于用简洁、专业的语言解答各种IT问题。",
        "Python专家": "你是Python编程专家，擅长代码生成、调试和解释。",
        "生活顾问": "你是生活小助手，擅长生活建议、健康、理财等领域。"
    }
    current_role = "默认"
    system_prompt = role_presets[current_role]
    print(f"\n===== 智能清理多轮对话模式 =====\n")
    print(f"AI 会根据您的目标生成初步清理计划，您可以多次提出修改意见或补充需求。\n")
    print(f"当您觉得计划满意时，请输入'同意清理'、'确认'、'可以执行'等同意性话语，AI 才会开始执行清理。\n输入'退出'可随时结束对话，不会执行任何清理操作。\n")
    # 添加初始用户目标到对话历史（如历史为空）
    if not conversation_history:
        conversation_history.append({"role": "user", "content": f"我的目标是：{goal}。请根据这个目标生成一个磁盘清理计划。"})
    while not plan_confirmed:
        try:
            print(f"当前目标: {goal}")
            print("\nAI 正在为您生成清理计划，请稍候...\n")
            print("候选垃圾目录:", junk_dirs)
            print("候选大文件:", large_file_paths)
            print("传递给AI的scan_result:", scan_result)
            plan = ai_planner.generate_plan(user_goal=goal, current_context=context, conversation_history=conversation_history)
            print("AI返回的plan:", plan)
            if not plan:
                logger.error("生成清理计划失败。")
                print("错误：生成清理计划失败。请检查API密钥和网络连接。")
                return
            # 显示生成的计划
            print("\n生成的清理计划如下：\n")
            # 格式化显示计划内容
            if isinstance(plan, dict) and plan.get("steps"):
                if len(plan["steps"]) == 0:
                    print("未发现可清理项，或AI未能生成清理建议。")
                else:
                    print("AI 生成的清理计划:")
                for i, step in enumerate(plan["steps"]):
                        path = step.get('path', '')
                        safety = step.get('safety', '')
                        reason = step.get('reason', '')
                        print(f"  步骤 {i+1}: 路径: {path}")
                        print(f"    建议: {safety}")
                        if reason:
                            print(f"    理由: {reason}")
                ai_response = "这是根据您当前需求生成的清理计划。如需调整，请直接回复您的意见。"
                conversation_history.append({"role": "assistant", "content": ai_response})
            elif isinstance(plan, dict) and plan.get("error"):
                print(f"AI未能生成清理建议：{plan.get('error')}")
            else:
                print("未发现可清理项，或AI未能生成清理建议。")
            # 友好提示
            print("\n如果计划需要修改，请直接输入您的意见或补充需求。")
            print("如果您同意当前计划，请输入'同意清理'、'确认'、'可以执行'等同意性话语。")
            print("如需退出，请输入'退出'。\n")
            # 获取用户输入
            try:
                if sys.stdin.isatty():
                    user_input = input("您的回复: ").strip()
                    if user_input.lower() == '退出':
                        logger.info("用户选择退出对话。"); print("对话已结束，未执行任何清理操作。\n"); return
                    elif user_input.lower() in ["清空记忆", "清空历史", "forget", "clear memory"]:
                        clear_conversation_history(history_file)
                        conversation_history = []
                        print("已清空对话历史。\n")
                        continue
                    elif user_input.startswith("你现在扮演") or user_input.startswith("切换角色"):
                        # 角色切换
                        role_name = user_input.replace("你现在扮演","").replace("切换角色","").strip()
                        if role_name in role_presets:
                            current_role = role_name
                            system_prompt = role_presets[current_role]
                            print(f"角色已切换：{current_role}")
                        else:
                            print(f"未找到角色预设：{role_name}，可用角色：{list(role_presets.keys())}")
                        continue
                    elif user_input.startswith("自定义角色：") or user_input.startswith("自定义角色:"):
                        # 自定义角色格式：自定义角色：角色名: prompt内容
                        parts = re.split(r"：|:", user_input, maxsplit=2)
                        if len(parts) == 3:
                            role_name = parts[1].strip()
                            prompt = parts[2].strip()
                            role_presets[role_name] = prompt
                            current_role = role_name
                            system_prompt = prompt
                            print(f"已添加并切换到自定义角色：{role_name}")
                        else:
                            print("自定义角色格式错误，应为：自定义角色：角色名: prompt内容")
                        continue
                    elif is_user_agree(user_input):
                        plan_confirmed = True
                        logger.info("用户同意清理计划。"); conversation_history.append({"role": "user", "content": user_input})
                    else:
                        conversation_history.append({"role": "user", "content": user_input})
                        logger.info(f"用户反馈: {user_input}")
                        # 判断用户输入是否与清理相关
                        if is_cleaning_related(user_input):
                            print("\nAI 正在根据您的反馈优化清理计划，请稍候...\n")
                        else:
                            # 用户输入与清理无关，进行通用聊天（多轮上下文+角色）
                            print("\nAI 正在回答您的问题，请稍候...\n")
                            chat_response = ai_planner._call_ai_model(
                                model_type=ai_planner.current_model,
                                model_name=ai_planner.model_name,
                                prompt=None,
                                system_prompt=system_prompt,
                                messages=conversation_history
                            )
                            if chat_response:
                                # 代码高亮显示+自动保存
                                if '```' in chat_response:
                                    import re
                                    code_blocks = re.findall(r'```([a-zA-Z]*)([\s\S]+?)```', chat_response)
                                    for lang, block in code_blocks:
                                        lang = lang.strip() or "py"
                                        filename = save_code_block(block.strip(), lang)
                                        print(f"\033[96m{block.strip()}\033[0m")  # 高亮
                                        print(f"[代码已自动保存到 {filename}]")
                                    print(chat_response)
                                else:
                                    print(f"AI回复: {chat_response}\n")
                                conversation_history.append({"role": "assistant", "content": chat_response})
                            else:
                                print("抱歉，AI暂时无法回答您的问题。\n")
                            print("您可以继续提问，或者回到清理计划讨论。")
                            print("如果您同意当前清理计划，请输入'同意清理'、'确认'等同意性话语。")
                            print("如需退出，请输入'退出'。\n")
                            # ==== 自动保存对话历史 ====
                            save_conversation_history(conversation_history, history_file)
                            continue  # 跳过重新生成清理计划，继续对话循环
                else:
                    logger.info("非交互式环境，自动确认清理计划。")
                    print("\n非交互式环境检测到，自动确认清理计划。\n")
                    plan_confirmed = True
                    conversation_history.append({"role": "user", "content": "我同意清理。"})
            except EOFError:
                logger.info("在非交互式环境中无法获取用户输入，自动确认清理计划。")
                print("\n非交互式环境检测到，自动确认清理计划。\n")
                plan_confirmed = True
                conversation_history.append({"role": "user", "content": "我同意清理。"})
            # ==== 自动保存对话历史 ====
            save_conversation_history(conversation_history, history_file)
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
    # 动态获取系统盘符作为默认路径
    import os
    system_drive = os.environ.get('SystemDrive', 'C:') + os.sep
    scan_paths = args.paths.split(',') if args.paths else [system_drive]
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
        
        # Save scan result to database
        if task_manager.save_scan_result():
            logger.info("扫描结果已保存到数据库。")
        else:
            logger.warning("保存扫描结果到数据库失败。")
        
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

def get_disk_usage(path=None):
    """获取磁盘使用情况"""
    if path is None:
        # 动态获取系统盘符
        import os
        path = os.environ.get('SystemDrive', 'C:') + os.sep
    usage = psutil.disk_usage(path)
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free
    }

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

    # ==== 新增：清理前空间统计 ====
    # 默认统计C盘，如需支持自定义可扩展
    before_usage = get_disk_usage()
    print(f"清理前可用空间: {before_usage['free'] / (1024**3):.2f} GB")
    # ==========================
    
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
        
        # ==== 新增：清理后空间统计 ====
        after_usage = get_disk_usage()
        freed = after_usage["free"] - before_usage["free"]
        print(f"清理后可用空间: {after_usage['free'] / (1024**3):.2f} GB")
        print(f"本次共释放空间: {freed / (1024**3):.2f} GB")
        # ==========================
        
        # ==== 新增：生成清理前后对比报告 ====
        try:
            from services.report_service import ReportService
            report_service = ReportService(app_context["config"], task_manager.db)
            # 获取 scan_id
            scan_id = args.scan_id
            comparison_report = report_service.generate_comparison_report(scan_id, task_id)
            if comparison_report:
                print("\n===== 清理前后对比报告摘要 =====")
                print(f"清理前总空间: {comparison_report['before_total_size'] / (1024**3):.2f} GB")
                print(f"清理后总空间: {comparison_report['after_total_size'] / (1024**3):.2f} GB")
                print(f"释放空间: {comparison_report['total_cleaned_size'] / (1024**3):.2f} GB")
                print(f"清理前文件数: {comparison_report['before_total_items']}，清理后文件数: {comparison_report['after_total_items']}")
                print("主要清理类别TOP5:")
                for cat, size in comparison_report['top_cleaned_categories']:
                    print(f"  {cat}: {size / (1024**3):.2f} GB")
                print("详细报告已保存到 reports 目录。\n")
        except Exception as e:
            logger.warning(f"生成清理前后对比报告失败: {e}")
        # ==========================
        
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

# --- Rules Command Implementation ---
def run_rules(args):
    from core.rules import RuleManager
    from config.manager import ConfigManager
    import yaml
    config = app_context["config"] or ConfigManager()
    rule_manager = RuleManager(config)
    if args.action == "list":
        rules = rule_manager.get_rules(enabled_only=False)
        print("\n===== 当前清理规则列表 =====\n")
        for i, r in enumerate(rules, 1):
            print(f"{i}. 名称: {r.name}")
            print(f"   匹配: {r.pattern}")
            print(f"   类别: {r.category}")
            print(f"   启用: {r.enabled}")
            print(f"   保留天数: {getattr(r, 'keep_days', '-')}")
            print(f"   描述: {r.description}")
            print("-------------------")
    elif args.action == "add":
        rule = {
            "name": args.name,
            "pattern": args.pattern,
            "category": args.category or "other",
            "enabled": not args.disabled,
            "description": args.description or "",
            "keep_days": args.keep_days or 0
        }
        # 直接写入yaml
        rules_path = os.path.join("config", "rules.yaml")
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        data.setdefault("rules", []).append(rule)
        with open(rules_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
        print(f"已添加规则: {rule['name']}")
    elif args.action == "remove":
        rules_path = os.path.join("config", "rules.yaml")
        if not os.path.exists(rules_path):
            print("未找到规则配置文件。"); return
        with open(rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules", [])
        rules = [r for r in rules if r.get("name") != args.name]
        data["rules"] = rules
        with open(rules_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
        print(f"已移除规则: {args.name}")
    elif args.action == "import":
        with open(args.file, "r", encoding="utf-8") as f:
            import_data = yaml.safe_load(f)
        rules_path = os.path.join("config", "rules.yaml")
        with open(rules_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(import_data, f, allow_unicode=True)
        print(f"已导入规则文件: {args.file}")
    elif args.action == "export":
        rules_path = os.path.join("config", "rules.yaml")
        if not os.path.exists(rules_path):
            print("未找到规则配置文件。"); return
        with open(rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        with open(args.file, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
        print(f"已导出规则到: {args.file}")
    else:
        print("未知规则操作。支持: list, add, remove, import, export")

def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # UI functionality has been removed as it was only placeholder code
    # return # Exit after UI closes

    
    # --- Main Argument Parser ---
    # If not launching UI, proceed with CLI argument parsing
    parser = argparse.ArgumentParser(description="C盘清理工具", prog="c_disk_cleaner")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # scan命令
    scan_parser = subparsers.add_parser("scan", help="扫描磁盘并分析空间使用情况")
    scan_parser.add_argument("--paths", help="要扫描的路径，用逗号分隔 (默认: 系统盘)")
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
    ai_plan_parser.add_argument("--model-name", help="指定更细致的AI底层模型（如 qwen-turbo, gemini-pro 等）")
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
    
    # rules命令
    rules_parser = subparsers.add_parser("rules", help="管理清理规则")
    rules_parser.add_argument("action", choices=["list", "add", "remove", "import", "export"], help="操作类型")
    rules_parser.add_argument("--name", help="规则名称 (add/remove)")
    rules_parser.add_argument("--pattern", help="匹配模式 (add)")
    rules_parser.add_argument("--category", help="文件类别 (add)")
    rules_parser.add_argument("--disabled", action="store_true", help="添加时禁用规则 (add)")
    rules_parser.add_argument("--description", help="规则描述 (add)")
    rules_parser.add_argument("--keep-days", type=int, help="保留天数 (add)")
    rules_parser.add_argument("--file", help="导入/导出文件路径 (import/export)")
    rules_parser.set_defaults(func=run_rules)
    
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


