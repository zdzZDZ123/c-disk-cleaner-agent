#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI规划专用入口点
简化的磁盘清理AI规划工具
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.ai_planner import AIPlannerService
from services.task_manager import TaskManager
from services.logger import LoggerService
from config.manager import ConfigManager
from core.scanner import Scanner
from core.rules import RuleManager
from data.database import Database

# 全局应用上下文
app_context = {}

def init_app():
    """初始化应用程序"""
    try:
        # 1. 初始化配置管理器（日志需要配置）
        config_manager = ConfigManager()
        app_context["config_manager"] = config_manager
        
        # 2. 初始化日志
        logger_service = LoggerService(config_manager)
        logger = logger_service.get_logger()
        app_context["logger"] = logger
        app_context["logger_service"] = logger_service
        logger.info("开始初始化AI规划应用...")
        logger.info("配置管理器初始化完成")
        
        # 3. 初始化数据库
        database = Database()
        app_context["database"] = database
        logger.info("数据库初始化完成")
        
        # 4. 初始化规则管理器
        rules_manager = RuleManager(config_manager)
        app_context["rules_manager"] = rules_manager
        logger.info("规则管理器初始化完成")
        
        # 5. 初始化扫描器
        scanner = Scanner(config_manager, rules_manager)
        app_context["scanner"] = scanner
        logger.info("扫描器初始化完成")
        
        # 6. 初始化任务管理器
        task_manager = TaskManager(config_manager, scanner)
        app_context["task_manager"] = task_manager
        logger.info("任务管理器初始化完成")
        
        # 7. 初始化AI规划服务
        ai_planner = AIPlannerService(config_manager)
        app_context["ai_planner"] = ai_planner
        
        if ai_planner.get_available_models():
            logger.info(f"AI规划服务初始化完成，可用模型: {ai_planner.get_available_models()}")
        else:
            logger.warning("AI规划服务初始化完成，但未找到可用模型")
            logger.warning("请确保在环境变量或配置文件中设置了有效的API密钥")
        
        logger.info("应用程序初始化完成")
        return True
        
    except Exception as e:
        if "logger" in app_context:
            app_context["logger"].error(f"应用程序初始化失败: {e}")
        else:
            print(f"应用程序初始化失败: {e}")
        return False

def cleanup_app():
    """清理应用程序资源"""
    logger = app_context.get("logger")
    
    try:
        # 关闭任务管理器
        if "task_manager" in app_context:
            app_context["task_manager"].close()
            if logger:
                logger.info("任务管理器已关闭。")
        
        # 清理其他资源
        app_context.clear()
        
        if logger:
            logger.info("应用程序已关闭。")
            
    except Exception as e:
        if logger:
            logger.error(f"清理应用程序时出错: {e}")
        else:
            print(f"清理应用程序时出错: {e}")

def run_ai_plan(args):
    """运行AI规划功能"""
    logger = app_context["logger"]
    ai_planner = app_context["ai_planner"]
    
    if not ai_planner:
        logger.error("AI服务未初始化，无法生成规划。")
        print("错误：AI服务未初始化。请确保配置了有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    
    # 显示可用模型信息
    available_models = ai_planner.get_available_models()
    if not available_models:
        logger.error("未找到任何可用的AI模型。")
        print("错误：未找到任何可用的AI模型。请确保至少配置了一个有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    
    print(f"\n可用的AI模型: {', '.join(available_models)}")
    
    # 处理模型选择
    if args.model:
        if args.model not in available_models:
            print(f"错误：指定的模型 '{args.model}' 不可用")
            print(f"可用模型: {', '.join(available_models)}")
            return
        ai_planner.set_model(args.model)
    
    # 处理具体模型名称
    if args.model_name:
        ai_planner.model_name = args.model_name
        print(f"使用模型: {args.model_name}")
    
    # 构建规划参数
    plan_params = {
        'goal': args.goal,
        'keep_days': args.keep_days
    }
    
    if args.paths:
        plan_params['paths'] = [p.strip() for p in args.paths.split(',')]
    
    if args.exclude:
        plan_params['exclude'] = [p.strip() for p in args.exclude.split(',')]
    
    print(f"\n开始生成AI清理规划...")
    print(f"目标: {args.goal}")
    print(f"保留天数: {args.keep_days}")
    
    try:
        # 启动AI规划任务
        task_manager = app_context["task_manager"]
        task_id = task_manager.start_ai_plan_task(**plan_params)
        
        if task_id:
            print(f"\nAI规划任务已启动，任务ID: {task_id}")
            print("您可以使用以下命令查看任务状态:")
            print(f"python app.py status {task_id}")
            print(f"python app.py result {task_id}")
        else:
            print("\n启动AI规划任务失败")
            
    except Exception as e:
        logger.error(f"AI规划执行失败: {e}")
        print(f"错误：AI规划执行失败: {e}")

def run_ai_chat(args):
    """运行AI通用问答功能"""
    logger = app_context["logger"]
    ai_planner = app_context["ai_planner"]
    
    if not ai_planner:
        logger.error("AI服务未初始化，无法进行对话。")
        print("错误：AI服务未初始化。请确保配置了有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    
    # 显示可用模型信息
    available_models = ai_planner.get_available_models()
    if not available_models:
        logger.error("未找到任何可用的AI模型。")
        print("错误：未找到任何可用的AI模型。请确保至少配置了一个有效的API密钥。")
        print("请运行 'python test_api_key.py' 检查API密钥设置。")
        return
    
    # 确定使用的模型
    if args.model_name:
        model_name = args.model_name
    else:
        # 使用默认推荐模型
        if "qwen" in available_models:
            model_name = "qwen-turbo"
        elif "gemini" in available_models:
            model_name = "gemini-pro"
        else:
            print("错误：没有可用的默认模型")
            return
    
    # 确定主模型类型
    if model_name.startswith("qwen"):
        model_type = "qwen"
    elif model_name.startswith("gemini"):
        model_type = "gemini"
    else:
        print(f"错误：无法识别模型类型: {model_name}")
        return
    
    print(f"\n=== AI智能助手 ({model_type.title()} {model_name}) ===")
    print("您可以向AI提问任何问题，输入'退出'或'quit'结束对话。\n")
    
    # 开始对话循环
    while True:
        try:
            user_input = input("您: ").strip()
            
            if user_input.lower() in ['退出', 'quit', 'exit', 'q']:
                print("\n再见！")
                break
            
            if not user_input:
                continue
            
            print("\nAI: ", end="", flush=True)
            
            # 调用AI模型进行问答
            try:
                response = ai_planner._call_ai_model(
                    model_type=model_type,
                    model_name=model_name,
                    prompt=user_input,
                    system_prompt="你是一个智能助手，可以回答用户的各种问题。请用中文回答，保持友好和专业的语调。"
                )
                
                if response:
                    print(response)
                else:
                    print("抱歉，我无法回答这个问题。")
                    
            except Exception as e:
                logger.error(f"AI问答失败: {e}")
                print(f"抱歉，处理您的问题时出现错误: {e}")
            
            print()  # 添加空行分隔
            
        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except EOFError:
            print("\n\n再见！")
            break

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='AI磁盘清理规划工具')
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # ai-plan 命令
    ai_plan_parser = subparsers.add_parser('ai-plan', help='生成AI清理计划')
    ai_plan_parser.add_argument('--goal', default='清理C盘，释放磁盘空间，重点关注临时文件、大文件和重复文件。',
                               help='清理目标描述')
    ai_plan_parser.add_argument('--model', choices=['qwen', 'gemini'],
                               help='指定AI模型类型')
    ai_plan_parser.add_argument('--model-name',
                               help='指定具体的模型名称（如qwen-turbo, gemini-pro等）')
    ai_plan_parser.add_argument('--paths',
                               help='要分析的路径，多个路径用逗号分隔')
    ai_plan_parser.add_argument('--exclude',
                               help='要排除的路径，多个路径用逗号分隔')
    ai_plan_parser.add_argument('--keep-days', type=int, default=30,
                               help='保留多少天内的文件（默认30天）')
    
    # ai-chat 命令
    ai_chat_parser = subparsers.add_parser('ai-chat', help='AI智能问答助手')
    ai_chat_parser.add_argument('--model', choices=['qwen', 'gemini'],
                               help='指定AI模型类型')
    ai_chat_parser.add_argument('--model-name',
                               help='指定具体的模型名称（如qwen-turbo, gemini-pro等）')
    
    # 如果没有参数，默认运行ai-plan
    if len(sys.argv) == 1:
        sys.argv.append('ai-plan')
    
    args = parser.parse_args()
    
    # 初始化应用
    if not init_app():
        sys.exit(1)
    
    # 根据命令执行相应操作
    if args.command == 'ai-plan':
        run_ai_plan(args)
    elif args.command == 'ai-chat':
        run_ai_chat(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序执行出错: {e}")
    finally:
        cleanup_app()