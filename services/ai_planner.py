#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
AI Planner Service - 与多种AI模型交互生成清理策略
支持的模型：Gemini、Qwen
"""

import requests
import os
import re
import json
import time
import urllib3
from typing import Dict, Any, Optional, List, Tuple, Literal
import getpass
from pathlib import Path

from config.manager import ConfigManager
from loguru import logger as loguru_logger # Use loguru directly for fallback and __main__

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class AIPlannerService:
    """与多种AI模型交互生成清理策略的服务"""

    def __init__(self, config_manager: Optional[ConfigManager] = None, model: str = "qwen", logger: Optional[Any] = None):
        """初始化AI规划服务

        Args:
            config_manager: 可选的ConfigManager实例
            model: 要使用的AI主模型，可选值：'gemini', 'qwen'
            logger: 可选的日志记录器实例
        """
        if config_manager is not None and not isinstance(config_manager, ConfigManager):
            raise TypeError("config_manager must be an instance of ConfigManager or None")
        if isinstance(config_manager, str):
            config_manager = ConfigManager(config_manager)
        self.config_manager = config_manager or ConfigManager()
        self.model = model
        self.logger = logger if logger else loguru_logger.bind(module="AIPlannerService_Fallback")
        self.api_keys = self._load_api_keys()
        self.network_config = self._detect_network_environment()
        # 推荐优先级列表
        self.model_priority = {
            "qwen": ["qwen-max", "qwen-turbo", "qwen-plus"],
            "gemini": ["gemini-pro", "gemini-1.5-pro", "gemini-1.5-flash"]
        }
        # --- 自动根据网络环境选择模型 ---
        if self.network_config.get("has_vpn", False) and "gemini" in self.api_keys:
            self.current_model = "gemini"
        elif "qwen" in self.api_keys:
            self.current_model = "qwen"
        elif "gemini" in self.api_keys:
            self.current_model = "gemini"
        else:
            self.current_model = self._get_first_available_model()
        self.api_key = self.api_keys.get(self.current_model)
        # 自动选择具体大模型
        self.model_name = self._auto_select_model_name(self.current_model)
        self.logger.info(f"AI Planner Service 成功初始化，使用{self.current_model}的{self.model_name}模型。")
        self.api_urls = {
            "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent",
            "qwen": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        }
        
        if self.api_key:
            self.logger.info(f"AI Planner Service 成功初始化，使用{self.current_model}的{self.model_name}模型。")
        else:
            self.logger.error(f"未找到任何可用的API密钥。AI Planner Service将无法正常工作。")

    def _load_api_keys(self) -> Dict[str, str]:
        """从环境变量或配置文件加载所有支持的AI模型API密钥"""
        api_keys = {}
        self.logger.info("开始加载AI模型API密钥...")
        # 尝试从环境变量加载
        gemini_env = os.getenv("GEMINI_API_KEY")
        qwen_env = os.getenv("QWEN_API_KEY")
        self.logger.info(f"环境变量 GEMINI_API_KEY: {'已设置' if gemini_env else '未设置'}")
        self.logger.info(f"环境变量 QWEN_API_KEY: {'已设置' if qwen_env else '未设置'}")
        if gemini_env:
            api_keys["gemini"] = gemini_env
            self.logger.info("从环境变量加载了Gemini API密钥")
        if qwen_env:
            api_keys["qwen"] = qwen_env
            self.logger.info("从环境变量加载了Qwen API密钥")
        # 尝试从配置文件加载
        try:
            if not self.config_manager or not hasattr(self.config_manager, 'get_config'):
                self.logger.error("配置管理器未初始化或无get_config方法，无法从配置文件加载API密钥")
                raise ValueError("配置管理器未初始化")
            config = self.config_manager.get_config()
            self.logger.info(f"配置文件加载状态: {'成功' if config else '失败'}")
            if not config or not isinstance(config, dict):
                self.logger.error("配置管理器返回了空配置或非字典")
                raise ValueError("配置为空")
                
            ai_config = {} # Initialize with empty dict
            if 'ai' not in config:
                self.logger.error("配置中不存在'ai'字段。AI Planner功能可能因此受限或不可用。")
                self.logger.info(f"已加载的配置文件的顶层包含以下字段: {list(config.keys())}")
                # ai_config remains empty, subsequent .get calls on it will return None or default
            else:
                ai_config = config.get("ai", {}) # If 'ai' exists, get it
            self.logger.info(f"AI配置字段: {list(ai_config.keys()) if ai_config else '空'}")
            
            # 检查各API密钥是否存在
            gemini_key = ai_config.get('gemini_api_key')
            qwen_key = ai_config.get('qwen_api_key')
            self.logger.info(f"配置文件中 gemini_api_key: {'已设置' if gemini_key else '未设置'}")
            self.logger.info(f"配置文件中 qwen_api_key: {'已设置' if qwen_key else '未设置'}")
            if gemini_key and "gemini" not in api_keys:
                api_keys["gemini"] = gemini_key
                self.logger.info("从配置文件加载了Gemini API密钥")
            if qwen_key and "qwen" not in api_keys:
                api_keys["qwen"] = qwen_key
                self.logger.info("从配置文件加载了Qwen API密钥")
        except Exception as e:
            self.logger.error(f"无法从配置文件加载API密钥: {e}")
            import traceback
            self.logger.error(f"错误详情: {traceback.format_exc()}")
            
        if not api_keys:
            self.logger.error("在环境变量或配置文件中未找到任何API密钥")
            self.logger.error("请确保在环境变量或config/default.yaml中设置了至少一个API密钥")
            self.logger.error("可以运行 'python test_api_key.py' 检查API密钥设置")
            # 只打印一次主要错误，避免重复输出
            return api_keys
        else:
            self.logger.info(f"成功加载的API模型: {list(api_keys.keys())}")
            
        return api_keys
        
    def _get_first_available_model(self) -> str:
        """获取第一个可用的模型名称，如果没有可用模型则返回'gemini'"""
        if self.api_keys:
            return next(iter(self.api_keys.keys()))
        return "gemini"  # 默认返回gemini
        
    def set_model(self, model: str) -> bool:
        """设置要使用的AI模型
        
        Args:
            model: 模型名称，可选值：'gemini', 'qwen'
            
        Returns:
            bool: 是否成功设置模型
        """
        if model not in ["gemini", "qwen"]:
            self.logger.error(f"不支持的模型: {model}")
            return False
        if model not in self.api_keys:
            self.logger.error(f"未找到{model}模型的API密钥")
            return False
        self.current_model = model
        self.api_key = self.api_keys[model]
        self.logger.info(f"已切换到{model.capitalize()}模型")
        return True
        
    def get_available_models(self) -> List[str]:
        """获取所有可用的AI模型列表"""
        return list(self.api_keys.keys())

    def check_api_reachable(self, model: str, timeout: int = 5) -> bool:
        """检测指定AI模型API是否可达（仅做提示，不影响实际调用）"""
        # 只做日志提示，不影响实际调用
        if model == "qwen":
            self.logger.info("Qwen网络可达性检测结果: %s" % self.network_config.get("can_access_qwen", False))
            return True
        elif model == "gemini":
            self.logger.info("Gemini网络可达性检测结果: %s" % self.network_config.get("can_access_gemini", False))
            return True
        else:
            return True

    def refresh_network_config(self):
        """重新检测网络环境配置（仅做提示，不影响实际调用）"""
        self.logger.info("重新检测网络环境...（仅做提示，不影响实际调用）")
        self.network_config = self._detect_network_environment()
        self.logger.info(f"网络环境检测结果: {self.network_config}")
        # 不再自动切换模型

    def auto_switch_model_by_network(self):
        """根据当前网络环境自动切换可用AI模型（仅做提示，不影响实际调用）"""
        self.logger.info("自动切换模型功能已禁用，始终允许用户选择模型。当前模型: %s" % self.current_model)
        return self.current_model

    def _is_valid_plan(self, plan: dict) -> bool:
        """判断plan是否为有效清理计划，兼容多种字段"""
        return (
            isinstance(plan, dict) and (
                "steps" in plan or
                "cleanup_plan" in plan or
                "actions" in plan or
                "plan" in plan or
                "thinking_process" in plan
            ) and plan.get("error") != "not_json"
        )

    def _normalize_plan(self, plan: dict) -> dict:
        """将cleanup_plan、actions、plan等字段自动转为steps"""
        if "cleanup_plan" in plan:
            plan["steps"] = plan.pop("cleanup_plan")
        elif "actions" in plan:
            plan["steps"] = plan.pop("actions")
        elif "plan" in plan:
            plan["steps"] = plan.pop("plan")
        return plan

    def generate_safety_labels(self, candidate_paths: list, user_goal: str = None, extra_context: dict = None) -> list:
        """让AI对已扫描路径做安全性分流标记（safe/confirm/forbid）"""
        system_prompt = {
            "role": "system",
            "content": (
                "你会收到一组已扫描的绝对路径（如：['C:\\Users\\xxx\\Downloads\\abc.zip', 'C:\\Windows\\Temp']），"
                "请只对这些路径做如下标记：safe（可自动清理）、confirm（需人工确认）、forbid（禁止清理）。"
                "输出格式如下：\n"
                "[{\"path\": \"C:\\Users\\xxx\\Downloads\\abc.zip\", \"safety\": \"confirm\", \"reason\": \"大文件，建议人工确认\"}, ...]\n"
                "禁止生成新的路径，只能对输入的路径做标记。"
            )
        }
        user_prompt = {"role": "user", "content": f"请对以下路径做分流标记：{json.dumps(candidate_paths, ensure_ascii=False)}"}
        messages = [system_prompt, user_prompt]
        if user_goal:
            messages.append({"role": "user", "content": f"用户目标：{user_goal}"})
        if extra_context:
            messages.append({"role": "system", "content": f"补充上下文：{json.dumps(extra_context, ensure_ascii=False)}"})
        # 只用当前模型一次
            if self.current_model == "gemini":
                plan = self._generate_plan_with_gemini_multi(messages)
            elif self.current_model == "qwen":
                plan = self._generate_plan_with_qwen_multi(messages)
            else:
                self.logger.error(f"不支持的模型: {self.current_model}")
            return []
        # 解析AI输出
        try:
            if isinstance(plan, str):
                plan = json.loads(plan)
            if isinstance(plan, list):
                return plan
            if isinstance(plan, dict) and 'steps' in plan:
                return plan['steps']
        except Exception as e:
            self.logger.error(f"AI分流输出解析失败: {e}")
        return []

    def generate_plan(self, user_goal: str = None, current_context: Optional[Dict[str, Any]] = None, conversation_history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
        """新版：先本地扫描候选路径，再AI分流标记，自动切换可用模型"""
        candidate_paths = []
        if current_context and 'scan_result' in current_context:
            scan_result = current_context['scan_result']
            for k in ['garbage_dirs', 'large_files', 'duplicate_images', 'blurry_images']:
                v = scan_result.get(k, [])
                if isinstance(v, list):
                    candidate_paths.extend(v)
        candidate_paths = list(set(candidate_paths))
        if not candidate_paths:
            self.logger.warning("未发现可分流的候选路径，返回空计划。")
            return {"error": "未发现可分流的候选路径。"}
        # 自动切换模型
        available_models = self.get_available_models()
        last_error = None
        for model in available_models:
            self.set_model(model)
            try:
                safety_labels = self.generate_safety_labels(candidate_paths, user_goal, current_context)
                if safety_labels:
                    return {"steps": safety_labels}
            except Exception as e:
                last_error = e
                self.logger.warning(f"模型 {model} 生成分流失败，尝试下一个模型。错误: {e}")
        # 本地兜底分流
        safety_labels = []
        for p in candidate_paths:
            p_lower = p.lower()
            if ('temp' in p_lower or 'cache' in p_lower or 
                p_lower.endswith(('.tmp', '.temp', '.bak', '.old', '.orig', '.swp', '.swo')) or
                'thumbs.db' in p_lower or 'desktop.ini' in p_lower or
                p_lower.endswith(('.log', '.out', '.err')) or
                p_lower.endswith(('.part', '.crdownload', '.download')) or
                'node_modules' in p_lower or '__pycache__' in p_lower or
                p_lower.endswith(('.pyc', '.pyo')) or '.git' in p_lower):
                safety_labels.append({"path": p, "safety": "safe", "reason": "临时/缓存/日志文件"})
            elif p_lower.endswith(('.zip', '.rar', '.7z', '.mp4', '.mkv', '.avi', '.mov')):
                safety_labels.append({"path": p, "safety": "confirm", "reason": "大文件，建议人工确认"})
            elif ('system32' in p_lower or 'syswow64' in p_lower or 
                  'windows\\system' in p_lower or 'program files' in p_lower):
                safety_labels.append({"path": p, "safety": "forbid", "reason": "系统关键文件"})
            else:
                safety_labels.append({"path": p, "safety": "confirm", "reason": "需人工确认"})
        if safety_labels:
            return {"steps": safety_labels}
        return {"error": f"所有AI模型均不可用。最后错误: {last_error}"}

    def _generate_plan_with_qwen_multi(self, messages: list) -> Optional[Dict[str, Any]]:
        """多轮对话风格调用Qwen"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": "qwen-turbo",
            "input": {
                "messages": messages
            },
            "parameters": {
                "result_format": "message",
                "temperature": 0.1,
                "max_tokens": 2000,
                "top_p": 0.8
            }
        }
        api_url = self.api_urls["qwen"]
        session = self._get_session_for_model("qwen")
        max_retries = 3
        base_delay = 2
        max_delay = 60
        retry_delay = base_delay
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"向Qwen发送多轮对话 (尝试 {attempt}/{max_retries})...")
                response = session.post(api_url, headers=headers, json=payload, timeout=(5, 30))
                if response.status_code == 200:
                    result = response.json()
                    try:
                        output = result["output"]
                        if "choices" in output:
                            choices = output["choices"]
                            if not isinstance(choices, list) or len(choices) == 0:
                                    continue
                            message = choices[0].get("message", {})
                            plan_text = message.get("content", "")
                        elif "text" in output and isinstance(output["text"], str):
                            plan_text = output["text"]
                        else:
                                continue
                        if not plan_text:
                                continue
                        extracted_json_str = self._extract_json_from_text(plan_text)
                        if extracted_json_str:
                            try:
                                plan = json.loads(extracted_json_str)
                                self.logger.info(f"从Qwen成功接收并解析多轮计划")
                                return plan
                            except (json.JSONDecodeError, KeyError, ValueError):
                                continue
                        else:
                            # 新增：直接返回原始文本（非清理问题时可用）
                            return plan_text
                    except (json.JSONDecodeError, KeyError, ValueError):
                            continue
                else:
                    continue
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return None

    def _detect_gemini_models(self):
        """自动探测当前API Key可用的Gemini模型和API版本"""
        api_versions = ["v1", "v1beta"]
        available_models = []
        for version in api_versions:
            url = f"https://generativelanguage.googleapis.com/{version}/models"
            headers = {"x-goog-api-key": self.api_keys.get("gemini", "")}
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if "models" in data:
                        for m in data["models"]:
                            model_name = m.get("name", "")
                            if model_name:
                                available_models.append((version, model_name.split("/")[-1]))
                else:
                    self.logger.warning(f"Gemini ListModels {version} 返回: {resp.status_code} {resp.text}")
            except Exception as e:
                self.logger.warning(f"Gemini ListModels {version} 异常: {e}")
        if not available_models:
            # 兜底
            available_models = [("v1", "gemini-1.5-pro"), ("v1", "gemini-1.5-flash"), ("v1beta", "gemini-pro")]
        self.logger.info(f"自动探测到可用Gemini模型: {available_models}")
        return available_models

    def _call_gemini_for_chat(self, messages: list, model_name: str) -> Optional[str]:
        """调用Gemini模型进行问答，自动切换API版本和模型"""
        available_models = self._detect_gemini_models()
        for version, mname in available_models:
            try:
                session = self._get_session_for_model("gemini")
                url = f"https://generativelanguage.googleapis.com/{version}/models/{mname}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_keys['gemini']
                }
                # 转换消息格式
                gemini_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        gemini_messages.append({
                            "role": "user",
                            "parts": [{"text": msg["content"]}]
                        })
                    else:
                        gemini_messages.append({
                            "role": msg["role"],
                            "parts": [{"text": msg["content"]}]
                        })
                data = {
                    "contents": gemini_messages,
                    "generationConfig": {
                        "temperature": 0.7,
                        "topK": 40,
                        "topP": 0.95,
                        "maxOutputTokens": 1024,
                    }
                }
                self.logger.info(f"尝试Gemini {version}/{mname} ...")
                response = session.post(url, headers=headers, json=data, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if "candidates" in result and result["candidates"]:
                        candidate = result["candidates"][0]
                        if "content" in candidate and "parts" in candidate["content"]:
                            parts = candidate["content"]["parts"]
                            if parts and "text" in parts[0]:
                                return parts[0]["text"]
                    else:
                        self.logger.warning(f"Gemini {version}/{mname} 返回无candidates: {result}")
                else:
                    self.logger.error(f"Gemini API调用失败，状态码: {response.status_code}，URL: {url}，返回: {response.text}")
                    if response.status_code == 404:
                        continue  # 尝试下一个模型
            except Exception as e:
                self.logger.error(f"Gemini API调用异常: {e}")
                continue
        return None

    def _generate_plan_with_gemini_multi(self, messages: list) -> Optional[Dict[str, Any]]:
        """使用Gemini模型生成多轮对话的清理计划，自动切换API版本和模型"""
        if not self.api_key:
            self.logger.error("未初始化API密钥，无法生成计划")
            return None
        available_models = self._detect_gemini_models()
        for version, mname in available_models:
            try:
                session = self._get_session_for_model("gemini")
                url = f"https://generativelanguage.googleapis.com/{version}/models/{mname}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_keys['gemini']
                }
                gemini_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        gemini_messages.append({
                            "role": "user",
                            "parts": [{"text": msg["content"]}]
                        })
                    else:
                        gemini_messages.append({
                            "role": msg["role"],
                            "parts": [{"text": msg["content"]}]
                        })
                data = {
                    "contents": gemini_messages,
                    "generationConfig": {
                        "temperature": 0.7,
                        "topK": 40,
                        "topP": 0.95,
                        "maxOutputTokens": 1024,
                    }
                }
                self.logger.info(f"尝试Gemini {version}/{mname} ...")
                response = session.post(url, headers=headers, json=data, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if "candidates" in result and result["candidates"]:
                        candidate = result["candidates"][0]
                        if "content" in candidate and "parts" in candidate["content"]:
                            parts = candidate["content"]["parts"]
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"]
                                extracted_json_str = self._extract_json_from_text(text)
                                if extracted_json_str:
                                    try:
                                        plan = json.loads(extracted_json_str)
                                        self.logger.info(f"从Gemini({version}/{mname})成功接收并解析多轮计划")
                                        return plan
                                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                                        self.logger.debug(f"解析Gemini响应失败: {e}")
                                else:
                                    return text
                    else:
                        self.logger.warning(f"Gemini {version}/{mname} 返回无candidates: {result}")
                else:
                    self.logger.error(f"Gemini API调用失败，状态码: {response.status_code}，URL: {url}，返回: {response.text}")
                    if response.status_code == 404:
                        continue  # 尝试下一个模型
            except Exception as e:
                self.logger.error(f"Gemini API调用异常: {e}")
                continue
        return None

    def _call_ai_model(self, model_type: str, model_name: str, prompt: str = None, system_prompt: str = None, messages: list = None) -> Optional[str]:
        """通用AI模型调用方法，自动切换可用模型，支持多轮上下文messages"""
        available_models = self.get_available_models()
        last_error = None
        for model in available_models:
            self.set_model(model)
            try:
                # 优先用多轮messages
                if messages:
                    # Gemini/Qwen都支持多轮消息格式
                    if model == "qwen":
                        resp = self._call_qwen_for_chat(messages, self.model_name)
                    elif model == "gemini":
                        resp = self._call_gemini_for_chat(messages, self.model_name)
                    else:
                        self.logger.error(f"不支持的模型类型: {model}")
                        continue
                else:
                    # 单轮兼容
                    msg_list = []
                    if system_prompt:
                        msg_list.append({"role": "system", "content": system_prompt})
                    if prompt:
                        msg_list.append({"role": "user", "content": prompt})
                    if model == "qwen":
                        resp = self._call_qwen_for_chat(msg_list, self.model_name)
                    elif model == "gemini":
                        resp = self._call_gemini_for_chat(msg_list, self.model_name)
                    else:
                        self.logger.error(f"不支持的模型类型: {model}")
                        continue
                if resp:
                    return resp
            except Exception as e:
                last_error = e
                self.logger.warning(f"模型 {model} 聊天失败，尝试下一个模型。错误: {e}")
        # 所有模型都失败，兜底自我介绍
        return "我是你的磁盘清理智能助手，可以帮你生成和执行清理计划，也能和你闲聊。"
    
    def _call_qwen_for_chat(self, messages: list, model_name: str) -> Optional[str]:
        """调用Qwen模型进行问答"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_keys['qwen']}"
        }
        payload = {
            "model": model_name,
            "input": {
                "messages": messages
            },
            "parameters": {
                "result_format": "message",
                "temperature": 0.7,
                "max_tokens": 2000,
                "top_p": 0.8
            }
        }
        
        try:
            session = self._get_session_for_model("qwen")
            response = session.post(self.api_urls["qwen"], headers=headers, json=payload, timeout=(5, 30))
            
            if response.status_code == 200:
                result = response.json()
                output = result.get("output", {})
                
                if "choices" in output:
                    choices = output["choices"]
                    if choices and len(choices) > 0:
                        message = choices[0].get("message", {})
                        return message.get("content", "")
                elif "text" in output:
                    return output["text"]
            else:
                self.logger.error(f"Qwen API调用失败，状态码: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Qwen API调用异常: {e}")
            
        return None
    
    def _extract_json_from_text(self, text: str) -> Optional[str]:
        """从文本中提取JSON字符串
        
        Args:
            text: 可能包含JSON的文本
            
        Returns:
            提取的JSON字符串，如果未找到则返回None
        """
        if not text or not isinstance(text, str):
            return None
        text = text.strip()
        # 1. 直接尝试解析
        try:
            json.loads(text)
            return text
        except Exception:
            pass
        # 2. 去除 markdown 代码块
        text = re.sub(r"^```json|^```|```$", "", text, flags=re.IGNORECASE).strip()
        # 3. 提取所有 {...} 或 [...]，优先最长的
        candidates = re.findall(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        candidates = sorted(candidates, key=len, reverse=True)
        for candidate in candidates:
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        # 4. 尝试去除前后自然语言，只保留第一个 { 和 最后一个 }
        if '{' in text and '}' in text:
            start = text.find('{')
            end = text.rfind('}') + 1
            json_candidate = text[start:end]
            try:
                json.loads(json_candidate)
                return json_candidate
            except Exception:
                pass
        if '[' in text and ']' in text:
            start = text.find('[')
            end = text.rfind(']') + 1
            json_candidate = text[start:end]
            try:
                json.loads(json_candidate)
                return json_candidate
            except Exception:
                pass
        return None
            
    def _detect_network_environment(self) -> Dict[str, Any]:
        """检测当前网络环境并配置相应的代理设置"""
        network_config = {
            "has_vpn": False,
            "can_access_gemini": False,
            "can_access_qwen": False,
            "gemini_session": None,
            "qwen_session": None
        }
        
        self.logger.info("开始检测网络环境...")
        
        # 创建不同的session配置
        # 1. 直连session（用于qwen无VPN时）
        direct_session = requests.Session()
        direct_session.verify = False  # 允许不验证SSL证书
        
        # 2. 代理session（用于gemini需要VPN时）
        proxy_session = requests.Session()
        proxy_session.verify = False
        
        # 检测是否有系统代理
        system_proxies = requests.utils.get_environ_proxies("https://www.google.com")
        if system_proxies:
            self.logger.info(f"检测到系统代理配置: {system_proxies}")
            proxy_session.proxies.update(system_proxies)
            network_config["has_vpn"] = True
        
        # 测试qwen API连接性
        self.logger.info("测试qwen API连接性...")
        qwen_accessible = self._test_api_connectivity("qwen", direct_session)
        if qwen_accessible:
            network_config["can_access_qwen"] = True
            network_config["qwen_session"] = direct_session
            self.logger.info("qwen API可通过直连访问")
        else:
            # 尝试通过代理访问qwen
            qwen_accessible_proxy = self._test_api_connectivity("qwen", proxy_session)
            if qwen_accessible_proxy:
                network_config["can_access_qwen"] = True
                network_config["qwen_session"] = proxy_session
                self.logger.info("qwen API可通过代理访问")
            else:
                self.logger.warning("qwen API无法访问")
        
        # 测试gemini API连接性
        self.logger.info("测试gemini API连接性...")
        gemini_accessible = self._test_api_connectivity("gemini", proxy_session)
        if gemini_accessible:
            network_config["can_access_gemini"] = True
            network_config["gemini_session"] = proxy_session
            self.logger.info("gemini API可通过代理访问")
        else:
            # 尝试直连访问gemini
            gemini_accessible_direct = self._test_api_connectivity("gemini", direct_session)
            if gemini_accessible_direct:
                network_config["can_access_gemini"] = True
                network_config["gemini_session"] = direct_session
                self.logger.info("gemini API可通过直连访问")
            else:
                self.logger.warning("gemini API无法访问")
        
        self.logger.info(f"网络环境检测完成: VPN={network_config['has_vpn']}, Gemini可用={network_config['can_access_gemini']}, Qwen可用={network_config['can_access_qwen']}")
        return network_config
    
    def _test_api_connectivity(self, model: str, session: requests.Session, timeout: int = 5) -> bool:
        """测试指定模型的API连接性"""
        try:
            if model == "qwen":
                # 测试qwen API
                url = "https://dashscope.aliyuncs.com"
                headers = {}
                if self.api_keys.get("qwen"):
                    headers["Authorization"] = f"Bearer {self.api_keys['qwen']}"
                response = session.get(url, headers=headers, timeout=timeout)
                # 增加状态码检查
                if response.status_code >= 500:
                    self.logger.warning(f"Qwen API服务器返回错误状态码: {response.status_code}")
                    return False
                return response.status_code < 500
            elif model == "gemini":
                # 测试gemini API
                url = "https://generativelanguage.googleapis.com"
                response = session.get(url, timeout=timeout)
                # 增加状态码检查
                if response.status_code >= 500:
                    self.logger.warning(f"Gemini API服务器返回错误状态码: {response.status_code}")
                    return False
                return response.status_code < 500
        except requests.exceptions.Timeout:
            self.logger.warning(f"测试{model} API连接超时")
            return False
        except requests.exceptions.ConnectionError as e:
            self.logger.warning(f"测试{model} API连接失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"测试{model} API时发生未知错误: {e}")
            return False
        return False
    
    def _get_session_for_model(self, model: str) -> requests.Session:
        """获取指定模型的最佳session配置"""
        if model == "qwen" and self.network_config.get("qwen_session"):
            return self.network_config["qwen_session"]
        elif model == "gemini" and self.network_config.get("gemini_session"):
            return self.network_config["gemini_session"]
        else:
            # 网络检测不可用时，返回默认session，始终允许尝试请求
            session = requests.Session()
            session.verify = False
            return session

    def _auto_select_model_name(self, main_model: str) -> str:
        """根据优先级自动选择可用的具体大模型"""
        # 这里假设API key可用即模型可用，实际可扩展为API探测
        if main_model in self.model_priority:
            for m in self.model_priority[main_model]:
                # 可扩展为API探测
                return m
        return self.model_priority[main_model][0] if main_model in self.model_priority else ""

if __name__ == '__main__':
    # 示例用法（需要设置API密钥或在配置文件中配置）
    import argparse
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="测试AI规划服务")
    parser.add_argument('--model', '-m', choices=['gemini', 'qwen', 'wenxin'], 
                        help="要使用的AI模型 (默认: 使用第一个可用的模型)")
    args = parser.parse_args()
    
    # For __main__ block, use a simple loguru logger configuration
    loguru_logger.remove()
    loguru_logger.add(lambda msg: print(msg, end=''), format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
    
    print("正在初始化AI规划服务...")
    # Pass the configured loguru_logger to AIPlannerService for testing purposes
    planner = AIPlannerService(model=args.model, logger=loguru_logger) if args.model else AIPlannerService(logger=loguru_logger)
    
    # 显示可用的模型
    available_models = planner.get_available_models()
    if available_models:
        print(f"可用的AI模型: {', '.join(available_models)}")
        print(f"当前使用的模型: {planner.current_model}")
    else:
        print("未找到任何可用的AI模型。请检查API密钥和配置。")
        exit(1)
    
    if planner.api_key:
        print("AI规划服务初始化成功。")
        goal = "清理我的下载文件夹，重点关注大型视频文件和旧的压缩包。"
        context = {
            "system_info": {"os": "Windows", "total_disk_space_gb": 500, "free_disk_space_gb": 100},
            "user_preferences": {"keep_files_newer_than_days": 30}
        }
        print(f"正在使用{planner.current_model.capitalize()}的{planner.model_name}模型生成清理计划，目标: {goal}")
        generated_plan = planner.generate_plan(user_goal=goal, current_context=context)

        if generated_plan:
            print("\n生成的清理计划:")
            print(json.dumps(generated_plan, indent=2, ensure_ascii=False))
            # 在清理计划输出时，自动遍历并列举所有可删除的路径（伪代码，实际应在UI/CLI展示层实现）
            # def print_deletable_paths(plan):
            #     if plan and 'steps' in plan:
            #         print('可删除的路径列表:')
            #         for idx, step in enumerate(plan['steps'], 1):
            #             if 'path' in step:
            #                 print(f"{idx}. {step['path']}")
        else:
            print("\n生成计划失败。")
            
            # 尝试切换到其他可用模型
            other_models = [m for m in available_models if m != planner.current_model]
            if other_models:
                print(f"\n尝试使用其他模型: {other_models[0]}")
                planner.set_model(other_models[0])
                print(f"已切换到{planner.current_model.capitalize()}的{planner.model_name}模型")
                
                print("重新尝试生成计划...")
                generated_plan = planner.generate_plan(user_goal=goal, current_context=context)
                
                if generated_plan:
                    print("\n生成的清理计划:")
                    print(json.dumps(generated_plan, indent=2, ensure_ascii=False))
                else:
                    print("\n使用备选模型生成计划也失败了。")
    else:
        print("AI规划服务无法初始化。请检查API密钥和配置。")

    # 日志示例
    loguru_logger.info("AI规划脚本执行完成。")