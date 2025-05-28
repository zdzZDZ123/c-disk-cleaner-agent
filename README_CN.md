# C盘智能清理工具

一款基于AI的Windows C盘智能清理工具，支持多轮对话、自动备份、自动模型切换和定时清理。

## 主要功能（2024）

- 🤖 **AI多模型智能规划**
  - 支持通义千问Qwen和Google Gemini大模型
  - 多轮自然语言对话优化清理计划
  - 自动切换模型（VPN/地区自适应）
  - 每个文件AI分级：`safe`（自动清理）、`confirm`（需确认）、`forbid`（禁止删除）
  - AI自动适配本机常见目录（如下载、桌面等）

- 🔍 **智能扫描与分析**
  - 自动发现系统垃圾、临时、浏览器、IM/下载/游戏等缓存目录
  - 大文件、重复文件智能识别与分组
  - 支持自定义扫描/排除路径、保留天数

- 🧹 **安全清理与备份**
  - 清理前自动备份，支持一键还原
  - 支持系统临时、浏览器缓存、下载、回收站等常见垃圾一键清理
  - 支持自定义清理规则（`config/rules.yaml`）

- 📊 **报告与统计**
  - 清理前后空间对比，自动统计释放空间
  - 详细清理报告，支持导出历史

- ⏰ **自动化与定时任务**
  - 支持定时自动清理（可配置周期、类别）
  - 命令行一键全自动/半自动清理

- 🛠️ **丰富命令行与日志**
  - 丰富命令行：`scan`、`clean`、`ai-plan`、`restore`、`list-backups`、`list-duplicates`、`schedule`、`rules`
  - 详细日志与错误提示，便于排查
  - 支持API密钥有效性检测脚本

## 安装方法

1. 克隆仓库：
```bash
git clone https://github.com/zdzZDZ123/c_disk_cleaner_agent.git
cd c_disk_cleaner_agent
```
2. 安装依赖：
```bash
pip install -r requirements.txt
```
3. 配置API密钥（Qwen和/或Gemini）：
   - 在`config/default.yaml`或环境变量中设置：
     ```bash
     $env:QWEN_API_KEY="你的Qwen密钥"
     $env:GEMINI_API_KEY="你的Gemini密钥"
     ```

## 常用命令示例

- 基本用法：
  ```bash
  python app.py
  ```
- AI多轮规划：
  ```bash
  python app.py ai-plan
  ```
- 扫描指定路径：
  ```bash
  python app.py scan --paths C:\Users\你的用户名\Downloads
  ```
- 按扫描ID清理：
  ```bash
  python app.py clean --scan-id 1
  ```
- 列出备份/重复文件：
  ```bash
  python app.py list-backups
  python app.py list-duplicates --scan-id 1
  ```
- 定时自动清理：
  ```bash
  python app.py schedule --enable --interval 14 --categories temp_files,cache_files
  ```
- 测试API密钥：
  ```bash
  python test_api_key.py --model qwen
  python test_api_key.py --model gemini
  ```

## AI规划与安全机制
- 通过`ai-plan`命令与AI多轮对话，支持反复调整目标
- 每一步清理都需用户确认，防止误删
- 所有清理操作默认自动备份，支持一键还原
- AI自动适配本机实际目录

## 配置说明
- API密钥：`config/default.yaml`或环境变量
- 清理规则：`config/rules.yaml`
- 定时任务：通过`schedule`命令或配置文件

## 常见问题与配额说明
- **API配额超限（429）**：如遇`RESOURCE_EXHAUSTED`或429错误，说明API配额已用尽，请前往Google/Aliyun控制台检查配额/账单，或等待重置。
- **网络/API密钥问题**：请确保能访问阿里云/Google，API密钥有效（可用`test_api_key.py`检测）
- **日志**：详细错误见`logs/app.log`

## 目录结构
```
├── app.py                # 主程序入口
├── config/
├── data/
├── services/
├── core/
├── test_api_key.py       # API密钥测试脚本
├── README_CN.md
└── requirements.txt
```

## 依赖环境
- Python 3.8+
- requests
- loguru
- google-generativeai>=0.5.0（Gemini专用）

## 开源协议
MIT

## 联系方式
- 项目主页：https://github.com/zdzZDZ123/c_disk_cleaner_agent
- 问题反馈：https://github.com/zdzZDZ123/c_disk_cleaner_agent/issues