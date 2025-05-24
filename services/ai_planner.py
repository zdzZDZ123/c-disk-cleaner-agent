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
            model: 要使用的AI模型，可选值：'gemini', 'qwen'
            logger: 可选的日志记录器实例
        """
        self.config_manager = config_manager or ConfigManager()
        self.model = model
        self.logger = logger if logger else loguru_logger.bind(module="AIPlannerService_Fallback")
        self.api_keys = self._load_api_keys()
        
        # 网络环境检测和代理配置
        self.network_config = self._detect_network_environment()
        
        # 优先选择qwen作为默认模型
        if "qwen" in self.api_keys:
            self.current_model = "qwen"
        elif model in self.api_keys:
            self.current_model = model
        else:
            self.current_model = self._get_first_available_model()
        self.api_key = self.api_keys.get(self.current_model)
        
        # 各模型的API URL
        self.api_urls = {
            "gemini": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            "qwen": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        }
        
        if self.api_key:
            self.logger.info(f"AI Planner Service 成功初始化，使用{self.current_model.capitalize()}模型。")
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
            if not self.config_manager:
                self.logger.error("配置管理器未初始化，无法从配置文件加载API密钥")
                raise ValueError("配置管理器未初始化")
                
            config = self.config_manager.get_config()
            self.logger.info(f"配置文件加载状态: {'成功' if config else '失败'}")
            
            if not config:
                self.logger.error("配置管理器返回了空配置")
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
        """检测指定AI模型API是否可达"""
        # 使用网络配置中的连接性检测结果
        if model == "qwen":
            return self.network_config.get("can_access_qwen", False)
        elif model == "gemini":
            return self.network_config.get("can_access_gemini", False)
        else:
            return False

    def refresh_network_config(self):
        """重新检测网络环境配置"""
        self.logger.info("重新检测网络环境...")
        self.network_config = self._detect_network_environment()
        
        # 根据新的网络环境选择最佳模型
        available_models = []
        if self.network_config.get("can_access_qwen") and "qwen" in self.api_keys:
            available_models.append("qwen")
        if self.network_config.get("can_access_gemini") and "gemini" in self.api_keys:
            available_models.append("gemini")
        
        if available_models:
            # 优先选择qwen
            if "qwen" in available_models:
                self.set_model("qwen")
            else:
                self.set_model(available_models[0])
            self.logger.info(f"根据网络环境自动选择模型: {self.current_model}")
        else:
            self.logger.warning("当前网络环境下没有可用的AI模型")

    def auto_switch_model_by_network(self):
        """根据当前网络环境自动切换可用AI模型"""
        # 优先使用当前模型
        if self.check_api_reachable(self.current_model):
            return self.current_model
        
        # 如果当前模型不可用，重新检测网络环境
        self.logger.info("当前模型不可用，重新检测网络环境...")
        self.refresh_network_config()
        
        # 检查是否有可用模型
        if self.check_api_reachable(self.current_model):
            return self.current_model
        
        self.logger.error("未检测到任何可用的AI模型API，请检查网络或API密钥")
        return None

    def generate_plan(self, user_goal: str, current_context: Optional[Dict[str, Any]] = None, conversation_history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
        """使用当前选择的AI模型生成清理计划"""
        # 自动检测并切换到可用模型
        self.auto_switch_model_by_network()
        if not self.api_key:
            self.logger.error("未初始化API密钥，无法生成计划。请检查环境变量或配置文件中的API密钥设置。")
            return None

        # ==== 新增：动态检测本机下载目录 ====
        user_name = getpass.getuser()
        download_path = Path.home() / "Downloads"
        if download_path.exists():
            download_path_str = str(download_path)
        else:
            # 回退到C盘根目录
            download_path_str = "C:\\"
        # 统一为双反斜杠格式，便于prompt替换
        download_path_str = download_path_str.replace("\\", "\\\\")
        # =============================

        # 构建提示词
        if conversation_history and len(conversation_history) > 0:
            # 如果有对话历史，则使用对话历史构建提示词
            prompt = self._build_prompt_with_history(user_goal, current_context, conversation_history)
            # 替换prompt中的默认路径
            prompt = prompt.replace("C:\\\\Users\\\\User\\\\Downloads", download_path_str)
        else:
            # 否则使用单轮对话提示词
            prompt = f"用户目标: {user_goal}\n\n"
            if current_context:
                prompt += f"当前上下文: {str(current_context)}\n\n"
            prompt += (r"根据用户目标和当前上下文，为磁盘清理代理制定一个逐步计划。"
                      r"该计划应指定诸如'scan_paths'、'identify_file_categories'、'suggest_deletions'、'perform_cleanup'等操作。"
                      r"\n\n**重要：你必须且只能返回JSON格式！**\n"
                      r"**严格要求：**\n"
                      r"1. 你必须且只能返回纯JSON格式，绝对不要添加任何解释文字、Markdown格式或代码块标记\n"
                      r"2. 绝对不要使用```json```包装，直接返回JSON对象\n"
                      r"3. 确保JSON格式完全正确，可以被json.loads()解析\n"
                      r"4. 不要在JSON前后添加任何文字说明\n"
                      r"5. 不要返回自然语言文本，只返回JSON\n\n"
                      r"必须严格按照以下JSON格式返回：\n"
                      r"{\n"
                      r'  "thinking_process": "详细的思考过程",\n'
                      r'  "steps": [\n'
                      r'    {\n'
                      r'      "action": "scan_paths",\n'
                      r'      "description": "扫描指定路径",\n'
                      r'      "parameters": {"paths": ["C:\\\\Users\\\\User\\\\Downloads"], "exclude_patterns": ["*.log"]}\n'
                      r'    },\n'
                      r'    {\n'
                      r'      "action": "identify_file_categories",\n'
                      r'      "description": "识别文件类别",\n'
                      r'      "parameters": {"categories": ["large_files", "temp_files", "duplicates"]}\n'
                      r'    }\n'
                      r'  ]\n'
                      r"}\n\n"
                      r"**再次强调：只返回上述JSON格式，不要添加任何其他内容！**")
            # 替换prompt中的默认路径
            prompt = prompt.replace("C:\\\\Users\\\\User\\\\Downloads", download_path_str)
        # ====== END PATCH ======

        # 尝试使用当前模型生成计划
        self.logger.info(f"正在使用{self.current_model.capitalize()}模型生成清理计划...")
        plan = None
        
        # 根据不同模型调用相应的API
        if self.current_model == "gemini":
            plan = self._generate_plan_with_gemini(prompt)
        elif self.current_model == "qwen":
            plan = self._generate_plan_with_qwen(prompt, conversation_history)
        else:
            self.logger.error(f"不支持的模型: {self.current_model}")
            return None
            
        # 如果当前模型失败，尝试切换到备用模型
        if plan is None and len(self.api_keys) > 1:
            backup_models = [model for model in self.api_keys.keys() if model != self.current_model]
            if backup_models:
                backup_model = backup_models[0]
                self.logger.info(f"使用{self.current_model.capitalize()}模型生成计划失败，正在尝试切换到{backup_model.capitalize()}模型...")
                
                # 临时切换模型
                original_model = self.current_model
                self.set_model(backup_model)
                
                # 使用备用模型尝试生成计划
                if self.current_model == "gemini":
                    plan = self._generate_plan_with_gemini(prompt)
                elif self.current_model == "qwen":
                    plan = self._generate_plan_with_qwen(prompt, conversation_history)
                
                # 如果备用模型也失败，切回原始模型
                if plan is None:
                    self.logger.warning(f"使用备用模型{backup_model.capitalize()}也失败了，切回{original_model.capitalize()}模型")
                    self.set_model(original_model)
                else:
                    self.logger.info(f"成功使用备用模型{backup_model.capitalize()}生成计划")
        
        # 最终检查结果
        if plan is None:
            self.logger.error("生成清理计划失败。请检查网络连接和API密钥设置，或稍后重试。")
            return None
            
        return plan
        
    def _build_prompt_with_history(self, user_goal: str, current_context: Optional[Dict[str, Any]], conversation_history: List[Dict[str, str]]) -> str:
        """根据对话历史构建提示词
        
        Args:
            user_goal: 用户的高级目标
            current_context: 当前上下文
            conversation_history: 对话历史列表
            
        Returns:
            构建好的提示词字符串
        """
        prompt = f"用户初始目标: {user_goal}\n\n"
        if current_context:
            prompt += f"当前上下文: {str(current_context)}\n\n"
            
        prompt += "对话历史:\n"
        for message in conversation_history:
            role = message.get('role', 'unknown')
            content = message.get('content', '')
            prompt += f"{role.capitalize()}: {content}\n"
        
        prompt += "\n"
        prompt += (r"根据用户目标、当前上下文和对话历史，为磁盘清理代理制定或调整逐步计划。"
                  r"请考虑用户在对话中提出的所有要求和反馈，确保计划符合用户的期望。"
                  r"该计划应指定诸如'scan_paths'、'identify_file_categories'、'suggest_deletions'、'perform_cleanup'等操作。"
                  r"\n\n**重要：请严格按照以下格式返回JSON对象，不要添加任何解释文字或Markdown格式：**\n\n"
                  r"```json\n"
                  r"{\n"
                  r'  "thinking_process": "详细的思考过程",\n'
                  r'  "steps": [\n'
                  r'    {\n'
                  r'      "action": "scan_paths",\n'
                  r'      "parameters": {"paths": ["C:\\\\Users\\\\User\\\\Downloads"], "exclude_patterns": ["*.log"]}\n'
                  r'    },\n'
                  r'    {\n'
                  r'      "action": "identify_file_categories",\n'
                  r'      "parameters": {"categories": ["large_files", "temp_files", "duplicates"]}\n'
                  r'    }\n'
                  r'  ]\n'
                  r"}\n"
                  r"```\n\n"
                  r"请注重安全性和效率，确保返回的是有效的JSON格式。")
        
        return prompt
            
    def _generate_plan_with_gemini(self, prompt: str) -> Optional[Dict[str, Any]]:
        """使用Gemini模型生成计划"""
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }
        params = {"key": self.api_key}
        api_url = self.api_urls["gemini"]
        
        # 获取适合Gemini的session配置
        session = self._get_session_for_model("gemini")
        
        # 添加重试机制
        max_retries = 3
        retry_delay = 2  # 初始延迟2秒
        
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"向Gemini发送提示 (尝试 {attempt}/{max_retries}): {prompt[:200]}...")
                
                response = session.post(api_url, headers=headers, params=params, 
                                        data=json.dumps(payload), timeout=(5, 30))
                
                if response.status_code == 200:
                    result = response.json()
                    plan_text = ""
                    try:
                        plan_text = result["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError, TypeError) as e:
                        self.logger.error(f"无法从Gemini响应中提取计划文本。结构可能不符合预期。错误: {e}")
                        self.logger.debug(f"完整的Gemini响应用于调试: {json.dumps(result, indent=2)[:500]}...")
                        if attempt < max_retries:
                            self.logger.info(f"将在{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        return None
                    
                    extracted_json_str = None
                    # Try to extract JSON from markdown code blocks ```json ... ```
                    match = re.search(r"```json\s*(\{[\s\S]*?\}|\{[\s\S]*?\})\s*```", plan_text, re.DOTALL)
                    if match:
                        extracted_json_str = match.group(1)
                    else:
                        # Try to extract from ``` ... ```
                        match = re.search(r"```\s*(\{[\s\S]*?\}|\{[\s\S]*?\})\s*```", plan_text, re.DOTALL)
                        if match:
                            extracted_json_str = match.group(1)
                        else:
                            stripped_plan_text = plan_text.strip()
                            if (stripped_plan_text.startswith("{") and stripped_plan_text.endswith("}")) or \
                               (stripped_plan_text.startswith("[") and stripped_plan_text.endswith("]")):
                                extracted_json_str = stripped_plan_text
                            else:
                                self.logger.warning(f"Gemini response does not appear to be well-formed JSON or markdown-JSON: {plan_text[:200]}...")
                                extracted_json_str = stripped_plan_text # Try parsing it anyway

                    if extracted_json_str:
                        try:
                            plan = json.loads(extracted_json_str)
                            self.logger.info(f"从Gemini成功接收并解析计划")
                            return plan
                        except json.JSONDecodeError as json_err:
                            self.logger.error(f"解析从Gemini提取的JSON失败: {json_err}\n"
                                              f"尝试解析的文本: {extracted_json_str[:200]}...\n"
                                              f"原始Gemini响应 (部分): {plan_text[:500]}...")
                            if attempt < max_retries:
                                self.logger.info(f"JSON解析失败，将在{retry_delay}秒后重试...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            return None
                    else:
                        self.logger.error(f"无法从Gemini响应中提取有效的JSON内容。原始文本 (部分): {plan_text[:500]}...")
                        if attempt < max_retries:
                            self.logger.info(f"无法提取JSON，将在{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        return None
                else:
                    error_msg = f"Gemini API返回状态码 {response.status_code}"
                    try:
                        error_detail = response.text
                        self.logger.error(f"{error_msg}: {error_detail}")
                    except:
                        self.logger.error(error_msg)
                    
                    # 根据状态码决定是否重试
                    if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries:
                        retry_delay = min(retry_delay * 2, 60)  # 最大延迟60秒
                        self.logger.info(f"服务器繁忙或暂时不可用，将在{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    elif response.status_code == 401:
                        self.logger.error("API密钥无效或已过期，请检查您的API密钥设置")
                        return None
                    else:
                        if attempt < max_retries:
                            self.logger.info(f"将在{retry_delay}秒后重试 (非特定HTTP错误)...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        return None
            
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"连接错误: {e}")
                if attempt < max_retries:
                    retry_delay = min(retry_delay * 2, 60)
                    self.logger.info(f"网络连接问题，将在{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                self.logger.error("无法连接到Gemini API服务器，请检查您的网络连接")
                return None
                
            except requests.exceptions.Timeout as e:
                self.logger.error(f"请求超时: {e}")
                if attempt < max_retries:
                    retry_delay = min(retry_delay * 2, 60)
                    self.logger.info(f"请求超时，将在{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                self.logger.error("请求Gemini API超时，服务器可能繁忙")
                return None
                
            except Exception as e:
                self.logger.error(f"使用Gemini生成计划时出错: {e}")
                import traceback
                self.logger.error(f"错误详情: {traceback.format_exc()}")
                if attempt < max_retries:
                    retry_delay = min(retry_delay * 2, 60)
                    self.logger.info(f"发生未知错误，将在{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                return None
        
        self.logger.error(f"所有 ({max_retries}) 次尝试使用Gemini生成计划均失败。")
        return None

    def _generate_plan_with_qwen(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
        """使用Qwen模型生成计划
        
        Args:
            prompt: 提示词
            conversation_history: 可选的对话历史列表
            
        Returns:
            生成的计划字典，如果失败则返回None
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 如果有对话历史，则直接使用对话历史构建消息列表
        # 否则使用单条提示词消息，并添加系统消息强制JSON输出
        if conversation_history and len(conversation_history) > 0:
            messages = conversation_history
        else:
            # 添加系统消息强制JSON输出
            messages = [
                {
                    "role": "system", 
                    "content": "你是一个专业的磁盘清理助手。你必须且只能返回有效的JSON格式响应，绝对不要返回任何其他格式的内容。不要使用markdown代码块，不要添加任何解释文字，直接返回纯JSON对象。"
                },
                {"role": "user", "content": prompt}
            ]
            
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
        
        # 获取适合Qwen的session配置
        session = self._get_session_for_model("qwen")
        
        # 添加重试机制
        max_retries = 3
        retry_delay = 2  # 初始延迟2秒
        
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"向Qwen发送提示 (尝试 {attempt}/{max_retries}): {prompt[:200]}...")
                
                # 设置超时，避免长时间等待
                response = session.post(api_url, headers=headers, json=payload, timeout=(5, 30))  # 连接超时5秒，读取超时30秒
                
                # 检查网络连接问题
                if response.status_code == 200:
                    result = response.json()
                    # 健壮性检查和详细异常处理
                    try:
                        # 检查output和choices字段是否存在且格式正确
                        if not isinstance(result, dict) or "output" not in result:
                            self.logger.error(f"Qwen响应结构异常: 缺少output字段。原始响应: {json.dumps(result, ensure_ascii=False)}")
                            if attempt < max_retries:
                                self.logger.info(f"将在{retry_delay}秒后重试...")
                                time.sleep(retry_delay)
                                retry_delay *= 2  # 指数退避
                                continue
                            return None
                            
                        output = result["output"]
                        # 兼容新老Qwen响应格式
                        if "choices" in output:
                            choices = output["choices"]
                            if not isinstance(choices, list) or len(choices) == 0:
                                self.logger.error(f"Qwen响应choices字段为空或格式错误。原始响应: {json.dumps(result, ensure_ascii=False)}")
                                if attempt < max_retries:
                                    self.logger.info(f"将在{retry_delay}秒后重试...")
                                    time.sleep(retry_delay)
                                    retry_delay *= 2
                                    continue
                                return None
                                
                            message = choices[0].get("message", {})
                            plan_text = message.get("content", "")
                        elif "text" in output and isinstance(output["text"], str):
                            plan_text = output["text"]
                        else:
                            self.logger.error(f"Qwen响应output字段格式异常，未找到choices或text。原始响应: {json.dumps(result, ensure_ascii=False)}")
                            if attempt < max_retries:
                                self.logger.info(f"将在{retry_delay}秒后重试...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            return None
                            
                        if not plan_text:
                            self.logger.error(f"Qwen响应内容为空。原始响应: {json.dumps(result, ensure_ascii=False)}")
                            if attempt < max_retries:
                                self.logger.info(f"将在{retry_delay}秒后重试...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            return None
                            
                        # 提取JSON内容
                        extracted_json_str = None
                        # Try to extract JSON from markdown code blocks ```json ... ```
                        match = re.search(r"```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", plan_text, re.DOTALL)
                        if match:
                            extracted_json_str = match.group(1)
                        else:
                            # Try to extract from ``` ... ```
                            match = re.search(r"```\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", plan_text, re.DOTALL)
                            if match:
                                extracted_json_str = match.group(1)
                            else:
                                stripped_plan_text = plan_text.strip()
                                if (stripped_plan_text.startswith("{") and stripped_plan_text.endswith("}")) or \
                                   (stripped_plan_text.startswith("[") and stripped_plan_text.endswith("]")):
                                    extracted_json_str = stripped_plan_text
                                else:
                                    self.logger.warning(f"Qwen响应既不是Markdown JSON也不是原始JSON对象/数组: {plan_text[:200]}...")

                        if extracted_json_str:
                            try:
                                plan = json.loads(extracted_json_str)
                                self.logger.info(f"从Qwen成功接收并解析计划")
                                return plan
                            except json.JSONDecodeError as json_err:
                                self.logger.error(f"解析从Qwen提取的JSON失败: {json_err}\n"
                                                  f"尝试解析的文本: {extracted_json_str[:200]}...\n"
                                                  f"原始Qwen响应 (部分): {plan_text[:500]}...")
                        else:
                            self.logger.error(f"无法从Qwen响应中提取有效的JSON内容。原始文本 (部分): {plan_text[:500]}...")
                    # Fall through to retry or return None
                            if attempt < max_retries:
                                self.logger.info(f"将在{retry_delay}秒后重试...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            return None
                            
                    except (KeyError, IndexError, TypeError) as e:
                        self.logger.error(f"解析Qwen响应时出错: {e}")
                        self.logger.error(f"Qwen原始响应内容: {json.dumps(result, ensure_ascii=False)[:500]}...")
                        if attempt < max_retries:
                            self.logger.info(f"将在{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        return None
                else:
                    # 处理非200状态码
                    error_msg = f"Qwen API返回状态码 {response.status_code}"
                    try:
                        error_detail = response.text
                        self.logger.error(f"{error_msg}: {error_detail}")
                    except:
                        self.logger.error(error_msg)
                    
                    # 根据状态码决定是否重试
                    if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries:
                        retry_delay = min(retry_delay * 2, 60)  # 最大延迟60秒
                        self.logger.info(f"服务器繁忙或暂时不可用，将在{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    elif response.status_code == 401:  # 20 spaces
                        self.logger.error("API密钥无效或已过期，请检查您的API密钥设置")  # 24 spaces
                        return None  # 24 spaces
                    else:  # This 'else' corresponds to the 'if/elif' chain for status codes, 20 spaces from file start
                        if attempt < max_retries:  # 24 spaces from file start
                            self.logger.info(f"将在{retry_delay}秒后重试...")  # 28 spaces from file start
                            time.sleep(retry_delay)  # 28 spaces from file start
                            retry_delay *= 2  # 28 spaces from file start
                            continue  # 28 spaces from file start
                        return None  # 24 spaces from file start
                        
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"连接错误: {e}")
                if attempt < max_retries:
                    retry_delay = min(retry_delay * 2, 60)
                    self.logger.info(f"网络连接问题，将在{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                self.logger.error("无法连接到Qwen API服务器，请检查您的网络连接")
                return None
                
            except requests.exceptions.Timeout as e:
                self.logger.error(f"请求超时: {e}")
                if attempt < max_retries:
                    retry_delay = min(retry_delay * 2, 60)
                    self.logger.info(f"请求超时，将在{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                self.logger.error("请求Qwen API超时，服务器可能繁忙")
                return None
                
            except Exception as e:
                self.logger.error(f"使用Qwen生成计划时出错: {e}")
                import traceback
                self.logger.error(f"错误详情: {traceback.format_exc()}")
                if attempt < max_retries:
                    retry_delay = min(retry_delay * 2, 60)
                    self.logger.info(f"发生未知错误，将在{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                return None
                
        # 所有重试都失败
        self.logger.error(f"在{max_retries}次尝试后仍无法从Qwen获取有效响应")
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
                return response.status_code < 500
            elif model == "gemini":
                # 测试gemini API
                url = "https://generativelanguage.googleapis.com"
                response = session.get(url, timeout=timeout)
                return response.status_code < 500
        except Exception as e:
            self.logger.debug(f"测试{model} API连接失败: {e}")
            return False
        return False
    
    def _get_session_for_model(self, model: str) -> requests.Session:
        """获取指定模型的最佳session配置"""
        if model == "qwen" and self.network_config.get("qwen_session"):
            return self.network_config["qwen_session"]
        elif model == "gemini" and self.network_config.get("gemini_session"):
            return self.network_config["gemini_session"]
        else:
            # 返回默认session
            session = requests.Session()
            session.verify = False
            return session

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
        print(f"正在使用{planner.current_model.capitalize()}模型生成清理计划，目标: {goal}")
        generated_plan = planner.generate_plan(user_goal=goal, current_context=context)

        if generated_plan:
            print("\n生成的清理计划:")
            print(json.dumps(generated_plan, indent=2, ensure_ascii=False))
        else:
            print("\n生成计划失败。")
            
            # 尝试切换到其他可用模型
            other_models = [m for m in available_models if m != planner.current_model]
            if other_models:
                print(f"\n尝试使用其他模型: {other_models[0]}")
                planner.set_model(other_models[0])
                print(f"已切换到{planner.current_model.capitalize()}模型")
                
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