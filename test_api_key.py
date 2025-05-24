#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试AI模型API密钥是否有效
支持的模型：Gemini、Qwen
"""

import os
import sys
import json
import requests
from pathlib import Path

def load_api_keys_from_config():
    """从配置文件加载所有API密钥"""
    config_path = Path(os.path.expanduser('~')) / '.c_disk_cleaner' / 'config.yaml'
    if not config_path.exists():
        return {}
        
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        api_keys = {}
        if config and 'ai' in config:
            # 加载Gemini API密钥
            if 'gemini_api_key' in config['ai']:
                gemini_key = config['ai']['gemini_api_key']
                if gemini_key and gemini_key != 'YOUR_API_KEY_HERE':
                    api_keys['gemini'] = gemini_key
            
            # 加载Qwen API密钥
            if 'qwen_api_key' in config['ai']:
                qwen_key = config['ai']['qwen_api_key']
                if qwen_key and qwen_key != 'YOUR_API_KEY_HERE':
                    api_keys['qwen'] = qwen_key
        
        return api_keys
    except Exception as e:
        print(f"读取配置文件时出错: {e}", file=sys.stderr)
    
    return {}

def test_gemini_api_key(api_key):
    """测试Gemini API密钥是否有效"""
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Hello, Gemini!"}
                ]
            }
        ]
    }
    params = {"key": api_key}
    
    try:
        response = requests.post(api_url, headers=headers, params=params, data=json.dumps(payload))
        if response.status_code == 200:
            return True, "API密钥有效！"
        else:
            return False, f"API密钥无效。错误: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"测试API密钥时出错: {e}"  # 详细异常输出

def test_qwen_api_key(api_key):
    """测试Qwen API密钥是否有效"""
    api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "qwen-turbo",
        "input": {
            "messages": [
                {"role": "user", "content": "Hello, Qwen!"}
            ]
        }
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        if response.status_code == 200:
            return True, "API密钥有效！"
        else:
            return False, f"API密钥无效。错误: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"测试API密钥时出错: {e}"  # 详细异常输出

def main():
    import argparse
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="测试AI模型API密钥是否有效")
    parser.add_argument('--model', '-m', choices=['gemini', 'qwen', 'all'], 
                        default='all', help="要测试的AI模型 (默认: all)")
    args = parser.parse_args()
    
    # 获取所有API密钥
    api_keys = {}
    env_keys = {}
    
    # 从环境变量获取API密钥
    if os.environ.get('GEMINI_API_KEY'):
        env_keys['gemini'] = os.environ.get('GEMINI_API_KEY')
    if os.environ.get('QWEN_API_KEY'):
        env_keys['qwen'] = os.environ.get('QWEN_API_KEY')
    
    # 从配置文件获取API密钥
    config_keys = load_api_keys_from_config()
    
    # 合并环境变量和配置文件中的API密钥，环境变量优先
    for model in ['gemini', 'qwen']:
        if model in env_keys:
            api_keys[model] = {'key': env_keys[model], 'source': '环境变量'}
        elif model in config_keys:
            api_keys[model] = {'key': config_keys[model], 'source': '配置文件'}
    
    # 根据选择的模型进行测试
    models_to_test = [args.model] if args.model != 'all' else ['gemini', 'qwen']
    success_count = 0
    test_count = 0
    
    print("\n===== AI模型API密钥测试 =====\n")
    
    for model in models_to_test:
        if model not in api_keys:
            print(f"⚠ {model.capitalize()} API密钥未设置")
            print(f"  请通过以下方式之一设置{model.capitalize()}的API密钥:")
            if model == 'gemini':
                print("  1. 设置环境变量: $env:GEMINI_API_KEY=\"您的API密钥\"")
                print("  2. 在config/default.yaml文件中设置: ai.gemini_api_key")
            elif model == 'qwen':
                print("  1. 设置环境变量: $env:QWEN_API_KEY=\"您的API密钥\"")
                print("  2. 在config/default.yaml文件中设置: ai.qwen_api_key")
            print()
            continue
        
        test_count += 1
        print(f"测试 {model.capitalize()} API密钥 (来自{api_keys[model]['source']})...")
        
        if model == 'gemini':
            success, message = test_gemini_api_key(api_keys[model]['key'])
        elif model == 'qwen':
            success, message = test_qwen_api_key(api_keys[model]['key'])
        else:
            print(f"未知模型: {model}", file=sys.stderr)
            continue
        
        if success:
            print(f"✓ {model.capitalize()}: {message}")
            success_count += 1
        else:
            print(f"✗ {model.capitalize()}: {message}")
        print()
    
    # 总结
    if test_count == 0:
        print("未找到任何API密钥进行测试!")
        print("请在config/default.yaml文件中设置至少一个AI模型的API密钥")
        print("或者通过环境变量设置相应的API密钥。")
        print("\n详细说明请参考: README_AI_PLAN.md")
        return 1
    elif success_count > 0:
        print(f"✓ 成功验证了 {success_count}/{test_count} 个API密钥")
        print("现在您可以运行 'python app_new.py ai-plan' 命令了。")
        return 0
    else:
        print("✗ 所有API密钥验证失败")
        print("\n请检查您的API密钥是否正确，或者尝试获取新的API密钥。")
        print("详细说明请参考: README_AI_PLAN.md")
        return 1

if __name__ == "__main__":
    sys.exit(main())