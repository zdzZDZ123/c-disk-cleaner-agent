#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import unittest
from pathlib import Path
from loguru import logger

from core.scanner import Scanner
from config.manager import ConfigManager

class TestScanner(unittest.TestCase):
    def setUp(self):
        """测试前的准备工作"""
        self.config = ConfigManager()
        # 动态调整配置参数，便于测试
        self.config.set('rules.large_files.min_size_mb', 1)
        self.config.set('scanner.duplicate_min_size_mb', 1)
        self.config.set('rules.old_files.enabled', True)
        self.scanner = Scanner(self.config, process_delay=0.02)
        
        # 创建测试目录结构
        self.test_dir = Path("test_data")
        self.test_dir.mkdir(exist_ok=True)
        
        # 创建一些测试文件
        self._create_test_files()
        
    def tearDown(self):
        """测试后的清理工作"""
        # 停止扫描
        if self.scanner.is_scanning():
            self.scanner.stop_scan()
            
        # 清理测试文件
        if self.test_dir.exists():
            for file in self.test_dir.glob("**/*"):
                if file.is_file():
                    try:
                        if os.name == 'nt':  # Windows
                            import ctypes
                            ctypes.windll.kernel32.SetFileAttributesW(str(file), 0)  # Normal
                        file.unlink()
                    except Exception as e:
                        logger.warning(f"无法删除文件 {file}: {e}")
            try:
                self.test_dir.rmdir()
            except Exception as e:
                logger.warning(f"无法删除目录 {self.test_dir}: {e}")
            
    def _create_test_files(self):
        """创建测试用的文件结构"""
        # 创建临时文件
        (self.test_dir / "temp.tmp").write_text("temporary file content")
        (self.test_dir / "backup.bak").write_text("backup file content")
        
        # 创建大文件
        large_file = self.test_dir / "large_file.dat"
        with open(large_file, "wb") as f:
            f.write(b"0" * (1024 * 1024))  # 1MB文件
            
        # 创建重复文件
        content = "duplicate file content" * 100000  # >1MB
        (self.test_dir / "duplicate1.txt").write_text(content)
        (self.test_dir / "duplicate2.txt").write_text(content)
        
        # 创建更多文件以增加扫描时间
        for i in range(100):
            (self.test_dir / f"test_file_{i}.txt").write_text(f"test content {i}")
            
        # 创建日志文件
        (self.test_dir / "app.log").write_text("log content")
        (self.test_dir / "error.log.1").write_text("old log content")
        
        # 创建缓存文件
        (self.test_dir / "cache.cache").write_text("cache content")
        
        # 创建只读文件
        read_only = self.test_dir / "readonly.txt"
        # 写入前先删除同名文件并移除只读属性
        if read_only.exists():
            try:
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(read_only), 0)
                read_only.unlink()
            except Exception:
                pass
        read_only.write_text("read only content")
        if os.name == 'nt':  # Windows
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(read_only), 1)  # FILE_ATTRIBUTE_READONLY
            except Exception:
                logger.warning("无法设置只读属性")
        else:  # Unix-like
            try:
                read_only.chmod(0o444)
            except Exception:
                logger.warning("无法设置只读属性")
            
        # 创建旧文件（修改时间为30天前）
        old_file = self.test_dir / "old_file.txt"
        old_file.write_text("old content")
        old_time = time.time() - (30 * 24 * 60 * 60)  # 30天前
        try:
            os.utime(old_file, (old_time, old_time))
        except Exception:
            logger.warning("无法设置文件时间")

    def test_basic_scan(self):
        """测试基本扫描功能"""
        # 启动扫描
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        
        self.assertNotEqual(scan_id, "")
        self.assertTrue(self.scanner.is_scanning())
        
        # 等待扫描完成
        while self.scanner.is_scanning():
            items, size, progress = self.scanner.get_progress()
            logger.info(f"扫描进度: {progress:.2%}")
            time.sleep(0.5)
            
        # 获取结果
        result = self.scanner.get_current_result()
        self.assertIsNotNone(result)
        self.assertTrue(result.is_complete)
        
        # 验证扫描到的文件
        self.assertGreater(len(result.files), 0)
        
    def test_pause_resume(self):
        """测试暂停和恢复功能"""
        # 启动扫描
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        
        # 确保扫描已经开始
        self.assertTrue(self.scanner.is_scanning())
        
        # 等待一小段时间后暂停
        time.sleep(0.5)
        self.assertTrue(self.scanner.pause_scan())
        
        # 记录当前进度
        items1, size1, progress1 = self.scanner.get_progress()
        
        # 等待一段时间，确认进度没有变化
        time.sleep(2)
        items2, size2, progress2 = self.scanner.get_progress()
        self.assertEqual(items1, items2)
        
        # 恢复扫描
        self.assertTrue(self.scanner.resume_scan())
        
        # 等待扫描完成
        while self.scanner.is_scanning():
            time.sleep(0.5)
            
        # 验证最终结果
        result = self.scanner.get_current_result()
        self.assertTrue(result.is_complete)
        
    def test_stop_scan(self):
        """测试停止扫描功能"""
        # 启动扫描
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        
        # 确保扫描已经开始
        self.assertTrue(self.scanner.is_scanning())
        
        # 等待一小段时间后停止
        time.sleep(0.5)
        self.assertTrue(self.scanner.stop_scan())
        
        # 验证扫描已停止
        self.assertFalse(self.scanner.is_scanning())
        
        # 验证结果状态
        result = self.scanner.get_current_result()
        self.assertFalse(result.is_complete)

    def test_file_category(self):
        """测试文件分类功能"""
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        while self.scanner.is_scanning():
            time.sleep(0.2)
        result = self.scanner.get_current_result()
        self.assertIsNotNone(result)
        # 分类统计
        categories = set([f.category for f in result.files])
        from data.models import CleanCategory
        self.assertIn(CleanCategory.TEMP_FILES, categories)
        self.assertIn(CleanCategory.OTHER, categories)
        # 大文件
        has_large = any(f.size >= 1024*1024 and f.category == CleanCategory.LARGE_FILES for f in result.files)
        self.assertTrue(has_large)

    def test_duplicate_detection(self):
        """测试重复文件检测功能"""
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        while self.scanner.is_scanning():
            time.sleep(0.2)
        result = self.scanner.get_current_result()
        self.assertIsNotNone(result)
        # 检查重复文件集
        self.assertTrue(hasattr(result, 'duplicate_sets'))
        # duplicate1.txt 和 duplicate2.txt 应该被识别为重复
        found = False
        for group in getattr(result, 'duplicate_sets', []):
            names = [os.path.basename(p) for p in group]
            if 'duplicate1.txt' in names and 'duplicate2.txt' in names:
                found = True
        self.assertTrue(found)

    def test_file_categories(self):
        """测试所有文件类型的分类"""
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        while self.scanner.is_scanning():
            time.sleep(0.2)
        result = self.scanner.get_current_result()
        
        # 获取所有文件类别
        categories = {}
        for file in result.files:
            if file.category not in categories:
                categories[file.category] = []
            categories[file.category].append(file.name)
            
        # 验证各类文件是否被正确分类
        from data.models import CleanCategory
        self.assertIn(CleanCategory.TEMP_FILES, categories)
        # 日志文件和缓存文件会被归为OTHER类别
        self.assertIn(CleanCategory.OTHER, categories)
        self.assertIn(CleanCategory.LARGE_FILES, categories)
        self.assertIn(CleanCategory.OLD_FILES, categories)
        
        # 验证具体文件分类
        temp_files = categories[CleanCategory.TEMP_FILES]
        self.assertIn("temp.tmp", temp_files)
        self.assertIn("backup.bak", temp_files)
        
        # 日志和缓存文件应在OTHER类别中
        other_files = categories[CleanCategory.OTHER]
        self.assertIn("app.log", other_files)
        self.assertIn("error.log.1", other_files)
        self.assertIn("cache.cache", other_files)
        
        large_files = categories[CleanCategory.LARGE_FILES]
        self.assertIn("large_file.dat", large_files)
        
        old_files = categories[CleanCategory.OLD_FILES]
        self.assertIn("old_file.txt", old_files)

    def test_file_attributes(self):
        """测试文件属性识别"""
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir)],
            exclude_paths=[]
        )
        while self.scanner.is_scanning():
            time.sleep(0.2)
        result = self.scanner.get_current_result()
        
        # 查找只读文件
        read_only_files = [f for f in result.files if f.attributes.get('readonly', False)]
        self.assertTrue(any(f.name == "readonly.txt" for f in read_only_files))
        
        # 验证文件时间
        old_files = [f for f in result.files if f.name == "old_file.txt"]
        self.assertTrue(len(old_files) > 0)
        old_file = old_files[0]
        self.assertTrue(old_file.attributes.get('is_old', False))

    def test_error_handling(self):
        """测试错误处理"""
        # 测试无效路径
        scan_id = self.scanner.start_scan(
            scan_paths=[str(self.test_dir / "non_existent_dir")],
            exclude_paths=[]
        )
        while self.scanner.is_scanning():
            time.sleep(0.2)
        result = self.scanner.get_current_result()
        self.assertIsNotNone(result)
        self.assertTrue(result.is_complete)
        
        # 测试权限错误（创建无权限目录）
        if os.name == 'nt':  # Windows
            restricted_dir = self.test_dir / "restricted"
            restricted_dir.mkdir()
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(restricted_dir), 1)  # FILE_ATTRIBUTE_READONLY
                scan_id = self.scanner.start_scan(
                    scan_paths=[str(restricted_dir)],
                    exclude_paths=[]
                )
                while self.scanner.is_scanning():
                    time.sleep(0.2)
                result = self.scanner.get_current_result()
                self.assertIsNotNone(result)
                self.assertTrue(result.is_complete)
            finally:
                ctypes.windll.kernel32.SetFileAttributesW(str(restricted_dir), 0)  # Normal
                restricted_dir.rmdir()

if __name__ == '__main__':
    unittest.main() 