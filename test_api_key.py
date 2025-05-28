#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API密钥测试脚本
用于测试Qwen和Gemini API密钥的有效性
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.ai_planner import AIPlannerService
from config.manager import ConfigManager
from services.logger import setup_logger

def test_qwen_api(api_key):
    """测试Qwen API密钥"""
    try:
        import dashscope
        dashscope.api_key = api_key
        
        # 测试API调用
        response = dashscope.Generation.call(
            model='qwen-turbo',
            prompt='测试',
            max_tokens=10
        )
        
        if response.status_code == 200:
            print("✅ Qwen API密钥有效")
            return True
        else:
            print(f"❌ Qwen API调用失败: {response.message}")
            return False
            
    except ImportError:
        print("❌ 缺少dashscope依赖，请运行: pip install dashscope")
        return False
    except Exception as e:
        print(f"❌ Qwen API测试失败: {str(e)}")
        return False

def test_gemini_api(api_key):
    """测试Gemini API密钥"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # 测试API调用
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content('测试')
        
        if response.text:
            print("✅ Gemini API密钥有效")
            return True
        else:
            print("❌ Gemini API调用失败")
            return False
            
    except ImportError:
        print("❌ 缺少google-generativeai依赖，请运行: pip install google-generativeai")
        return False
    except Exception as e:
        print(f"❌ Gemini API测试失败: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='测试AI模型API密钥')
    parser.add_argument('--model', choices=['qwen', 'gemini', 'all'], 
                       default='all', help='要测试的模型')
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger()
    
    # 加载配置
    try:
        config_manager = ConfigManager()
        config = config_manager.get_config()
    except Exception as e:
        print(f"配置加载失败: {e}")
        return False
    
    print("=== API密钥测试 ===")
    
    success = True
    
    if args.model in ['qwen', 'all']:
        print("\n测试Qwen API...")
        
        # 从环境变量或配置文件获取API密钥
        qwen_key = os.getenv('QWEN_API_KEY')
        if not qwen_key and 'ai' in config and 'qwen_api_key' in config['ai']:
            qwen_key = config['ai']['qwen_api_key']
        
        if qwen_key:
            if not test_qwen_api(qwen_key):
                success = False
        else:
            print("❌ 未找到Qwen API密钥")
            print("   请设置环境变量QWEN_API_KEY或在config/default.yaml中配置")
            success = False
    
    if args.model in ['gemini', 'all']:
        print("\n测试Gemini API...")
        
        # 从环境变量或配置文件获取API密钥
        gemini_key = os.getenv('GEMINI_API_KEY')
        if not gemini_key and 'ai' in config and 'gemini_api_key' in config['ai']:
            gemini_key = config['ai']['gemini_api_key']
        
        if gemini_key:
            if not test_gemini_api(gemini_key):
                success = False
        else:
            print("❌ 未找到Gemini API密钥")
            print("   请设置环境变量GEMINI_API_KEY或在config/default.yaml中配置")
            success = False
    
    print("\n=== 测试完成 ===")
    
    if success:
        print("✅ 所有测试通过")
        return True
    else:
        print("❌ 部分测试失败，请检查API密钥配置")
        print("\n配置方法:")
        print("1. 环境变量:")
        print("   set QWEN_API_KEY=your_qwen_key")
        print("   set GEMINI_API_KEY=your_gemini_key")
        print("\n2. 配置文件 (config/default.yaml):")
        print("   ai:")
        print("     qwen_api_key: 'your_qwen_key'")
        print("     gemini_api_key: 'your_gemini_key'")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)