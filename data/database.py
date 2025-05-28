#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库接口 - 处理应用数据的持久化和检索
"""
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

class Database:
    """数据库管理类"""
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = Path.home() / ".c_disk_cleaner"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / "cleaner.db"
        self.db_path = str(db_path)
        self.conn = None
        self.init_database()

    def init_database(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()): 
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()): 
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None