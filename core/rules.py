#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则管理器 - 用于磁盘清理规则的定义与管理
"""

import re
from typing import List, Dict, Optional, Any
from config.manager import ConfigManager
import os

class Rule:
    """单条清理规则"""
    def __init__(self, name: str, pattern: str, category: str = "other", enabled: bool = True, description: str = ""):
        self.name = name
        self.pattern = pattern  # 支持通配符或正则
        self.category = category
        self.enabled = enabled
        self.description = description

    def match(self, file_path: str) -> bool:
        # 支持简单通配符和正则
        try:
            return re.search(self.pattern, file_path, re.IGNORECASE) is not None
        except re.error:
            return False

class RuleManager:
    """规则管理器，支持规则的增删查和批量加载"""
    def __init__(self, config_manager=None):
        if isinstance(config_manager, str):
            config_manager = ConfigManager(config_manager)
        self.rules: List[Rule] = []
        self.config_manager = config_manager
        self.load_rules_from_config()

    def load_rules_from_config(self):
        """从配置加载规则（如有）"""
        if self.config_manager and hasattr(self.config_manager, 'get'):
            config = self.config_manager.get("rules", [])
            for rule_item in config:
                if isinstance(rule_item, dict):
                    self.add_rule_from_dict(rule_item)
                elif isinstance(rule_item, str):
                    # 兼容老格式：直接字符串作为pattern
                    self.add_rule_from_dict({
                        "name": rule_item,
                        "pattern": rule_item,
                        "category": "other",
                        "enabled": True,
                        "description": f"自动兼容的规则：{rule_item}"
                    })
                else:
                    import warnings
                    warnings.warn(f"RuleManager: 未知规则格式，已跳过: {rule_item}")
        else:
            import warnings
            warnings.warn("RuleManager: config_manager无get方法，跳过规则加载。")

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def add_rule_from_dict(self, rule_dict: dict):
        if not isinstance(rule_dict, dict):
            import warnings
            warnings.warn(f"RuleManager: add_rule_from_dict收到非字典对象，已跳过: {rule_dict}")
            return
        rule = Rule(
            name=rule_dict.get("name", "unnamed"),
            pattern=rule_dict.get("pattern", ""),
            category=rule_dict.get("category", "other"),
            enabled=rule_dict.get("enabled", True),
            description=rule_dict.get("description", "")
        )
        self.add_rule(rule)

    def get_rules(self, category: Optional[str] = None, enabled_only: bool = True) -> List[Rule]:
        rules = self.rules
        if category:
            rules = [r for r in rules if r.category == category]
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules

    def match(self, file_path: str, category: Optional[str] = None) -> List[Rule]:
        """返回匹配该文件的所有规则"""
        return [r for r in self.get_rules(category) if r.match(file_path)]

    def remove_rule(self, name: str):
        self.rules = [r for r in self.rules if r.name != name]

    def clear_rules(self):
        self.rules = []

    def as_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": r.name,
                "pattern": r.pattern,
                "category": r.category,
                "enabled": r.enabled,
                "description": r.description
            }
            for r in self.rules
        ]

    def can_delete(self, file_item: 'FileItem', duplicate_sets: Optional[List[List[str]]] = None) -> bool:
        """判断文件是否可以安全删除
        
        Args:
            file_item: 文件项对象
            duplicate_sets: 重复文件集合列表，用于判断重复文件
            
        Returns:
            是否可以安全删除
        """
        # 检查文件是否在系统关键目录
        system_dirs = [
            "C:\\Windows",
            "C:\\Program Files",
            "C:\\Program Files (x86)",
            "C:\\ProgramData"
        ]
        if any(file_item.path.startswith(d) for d in system_dirs):
            return False
            
        # 检查文件是否在排除目录
        exclude_dirs = self.config_manager.get("scanner.exclude_dirs", [])
        if any(file_item.path.startswith(d) for d in exclude_dirs):
            return False
            
        # 检查文件是否在只扫描目录
        scan_only_dirs = []
        if self.config_manager.get("rules.temp_files.scan_only", True):
            scan_only_dirs.extend(self.config_manager.get("rules.temp_files.patterns", []))
        if self.config_manager.get("rules.large_files.scan_only", True):
            scan_only_dirs.extend(self.config_manager.get("rules.large_files.patterns", []))
        if self.config_manager.get("rules.duplicate_files.scan_only", True):
            scan_only_dirs.extend(self.config_manager.get("rules.duplicate_files.patterns", []))
            
        if any(self._match_pattern(file_item.path, p) for p in scan_only_dirs):
            return False
            
        # 检查是否是重复文件
        if duplicate_sets:
            for dup_set in duplicate_sets:
                if file_item.path in dup_set:
                    # 如果是重复文件，根据保留策略决定是否可删除
                    keep_strategy = self.config_manager.get("rules.duplicate_files.keep_strategy", "first")
                    if keep_strategy == "first":
                        return file_item.path != dup_set[0]
                    elif keep_strategy == "newest":
                        newest_file = max(dup_set, key=lambda x: os.path.getmtime(x))
                        return file_item.path != newest_file
                    elif keep_strategy == "oldest":
                        oldest_file = min(dup_set, key=lambda x: os.path.getmtime(x))
                        return file_item.path != oldest_file
                        
        return True
        
    def _match_pattern(self, path: str, pattern: str) -> bool:
        """匹配文件路径和模式
        
        Args:
            path: 文件路径
            pattern: 匹配模式
            
        Returns:
            是否匹配
        """
        try:
            return re.search(pattern, path, re.IGNORECASE) is not None
        except re.error:
            return False 