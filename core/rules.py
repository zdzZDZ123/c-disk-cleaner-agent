#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
规则管理器 - 文件分类与清理规则
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime, timedelta
from loguru import logger

from data.models import FileItem, FileType, CleanCategory
from config.manager import ConfigManager

class RuleManager:
    """规则管理器，负责文件分类与清理策略"""
    def __init__(self, config_manager=None):
        self.config = config_manager or ConfigManager()
        self.rules = []

    def categorize_file(self, file_item: FileItem) -> List[CleanCategory]:
        """根据文件特征分类"""
        categories = []
        if self._is_temp_file(file_item):
            categories.append(CleanCategory.TEMP_FILES)
        if self._is_browser_cache(file_item):
            categories.append(CleanCategory.BROWSER_CACHE)
        if self._is_windows_cache(file_item):
            categories.append(CleanCategory.WINDOWS_CACHE)
        if self._is_large_file(file_item):
            categories.append(CleanCategory.LARGE_FILES)
        return categories

    def can_delete(self, file_item: FileItem, duplicate_sets: Optional[List[List[str]]] = None) -> bool:
        """判断文件是否可删除"""
        if not file_item.can_delete:
            return False
        if duplicate_sets and self.config.get("rules.duplicate_files.enabled", True):
            for dup_set in duplicate_sets:
                if file_item.path in dup_set:
                    if dup_set.index(file_item.path) > 0:
                        return True
                    else:
                        return False
        categories = self.categorize_file(file_item)
        if not categories:
            return False
        for category in categories:
            if self._check_category_policy(category):
                return True
        return False

    def _check_category_policy(self, category: CleanCategory) -> bool:
        if category == CleanCategory.TEMP_FILES:
            return self.config.get("rules.temp_files.enabled", True)
        elif category == CleanCategory.BROWSER_CACHE:
            return self.config.get("rules.browser_cache.enabled", True)
        elif category == CleanCategory.WINDOWS_CACHE:
            return self.config.get("rules.windows_cache.enabled", True)
        elif category == CleanCategory.LARGE_FILES:
            return self.config.get("rules.large_files.enabled", True) and not self.config.get("rules.large_files.scan_only", True)
        elif category == CleanCategory.DUPLICATE_FILES:
            return self.config.get("rules.duplicate_files.enabled", True)
        elif category == CleanCategory.RECYCLE_BIN:
            return self.config.get("rules.recycle_bin.enabled", False)
        return False

    def _is_temp_file(self, file_item: FileItem) -> bool:
        patterns = self.config.get(
            "rules.temp_files.patterns", 
            ["*.tmp", "*.temp", "~*", "*.bak"]
        )
        for pattern in patterns:
            if self._match_pattern(file_item.name, pattern):
                return True
        return False

    def _is_browser_cache(self, file_item: FileItem) -> bool:
        paths = []
        if self.config.get("rules.browser_cache.chrome.enabled", True):
            chrome_paths = self.config.get(
                "rules.browser_cache.chrome.paths", 
                ["%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Cache"]
            )
            paths.extend([os.path.expandvars(p) for p in chrome_paths])
        if self.config.get("rules.browser_cache.edge.enabled", True):
            edge_paths = self.config.get(
                "rules.browser_cache.edge.paths", 
                ["%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Cache"]
            )
            paths.extend([os.path.expandvars(p) for p in edge_paths])
        for cache_path in paths:
            if file_item.path.startswith(cache_path):
                return True
        return False

    def _is_windows_cache(self, file_item: FileItem) -> bool:
        paths = self.config.get(
            "rules.windows_cache.paths", 
            ["C:\\Windows\\Temp", "%TEMP%", "%SYSTEMROOT%\\SoftwareDistribution\\Download"]
        )
        paths = [os.path.expandvars(p) for p in paths]
        for cache_path in paths:
            if file_item.path.startswith(cache_path):
                return True
        return False

    def _is_large_file(self, file_item: FileItem) -> bool:
        min_size_mb = self.config.get("rules.large_files.min_size_mb", 1000)
        min_size_bytes = min_size_mb * 1024 * 1024
        return file_item.size >= min_size_bytes

    def _match_pattern(self, file_name: str, pattern: str) -> bool:
        regex_pattern = pattern.replace(".", "\\.")
        regex_pattern = regex_pattern.replace("*", ".*")
        regex_pattern = regex_pattern.replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"
        return bool(re.match(regex_pattern, file_name, re.IGNORECASE))

