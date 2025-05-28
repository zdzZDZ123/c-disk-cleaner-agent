#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
配置管理器 - 处理程序配置的读取和写入
"""

import os
from pathlib import Path
import yaml
from loguru import logger


class ConfigManager:
    """配置管理器类"""
    
    def __init__(self, config_path=None):
        """初始化配置管理器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        self.default_config_path = Path(__file__).parent / "default.yaml"
        self.user_config_dir = Path.home() / ".c_disk_cleaner"
        self.user_config_path = self.user_config_dir / "config.yaml"
        self.config_path = config_path if config_path else self.user_config_path
        
        # 确保用户配置目录存在
        self.user_config_dir.mkdir(exist_ok=True)
        
        # 加载配置
        self.config = self.load_config()
    
    def load_config(self):
        """加载配置，优先使用用户配置，如果不存在则使用默认配置并复制一份"""
        try:
            # 如果用户配置不存在，复制默认配置
            if not self.user_config_path.exists():
                logger.info(f"用户配置不存在，创建默认配置: {self.user_config_path}")
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    default_config = yaml.safe_load(f)
                
                with open(self.user_config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)
                return default_config
            
            # 加载用户配置
            with open(self.config_path, 'r', encoding='utf-8') as f:
                logger.info(f"从 {self.config_path} 加载配置")
                return yaml.safe_load(f)
                
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            # 如果出错，尝试加载默认配置
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e2:
                logger.error(f"加载默认配置也失败: {e2}")
                return {}
    
    def save_config(self):
        """保存配置到用户配置文件"""
        try:
            with open(self.user_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"配置已保存至 {self.user_config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def get(self, key, default=None):
        """获取配置项
        
        支持使用点号分隔的路径，如 'scanner.exclude_dirs'
        
        Args:
            key: 配置键或路径
            default: 如果配置不存在时的默认值
        
        Returns:
            配置值或默认值
        """
        if not isinstance(self.config, dict):
            self.config = {}
            return default
        if '.' not in key:
            return self.config.get(key, default)
        
        parts = key.split('.')
        current = self.config
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        
        return current
    
    def set(self, key, value):
        """设置配置项
        
        支持使用点号分隔的路径，如 'scanner.exclude_dirs'
        
        Args:
            key: 配置键或路径
            value: 要设置的值
        
        Returns:
            操作是否成功
        """
        if '.' not in key:
            self.config[key] = value
            return True
        
        parts = key.split('.')
        current = self.config
        
        # 遍历路径直到倒数第二个部分
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # 设置最后一个部分的值
        current[parts[-1]] = value
        return True
    
    def update(self, config_dict):
        """更新多个配置项
        
        Args:
            config_dict: 包含配置项的字典
        """
        for key, value in config_dict.items():
            self.set(key, value)
    
    def get_api_key(self, service="gemini"):
        """获取API密钥
        
        Args:
            service: 服务名称，默认为"gemini"
            
        Returns:
            API密钥或None
        """
        return self.get(f'api.{service}.api_key')
    
    def get_project_id(self, service="gemini"):
        """获取项目ID
        
        Args:
            service: 服务名称，默认为"gemini"
            
        Returns:
            项目ID或None
        """
        return self.get(f'api.{service}.project_id') 
    
    def get_config(self):
        """获取完整配置字典"""
        return self.config