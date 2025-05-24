# C盘清理工具

## 功能简介

- 智能扫描磁盘空间，自动识别可清理文件
- 支持自定义扫描路径、排除规则和清理参数
- **AI智能规划（实验性）**：通过AI大模型（默认Qwen，备选Gemini）自动分析磁盘空间并生成清理建议
- 支持备份与还原，保障数据安全
- **自动适配本机下载目录**：AI规划会自动检测本机的下载目录（如 `C:\Users\你的用户名\Downloads`），不会再出现路径不存在的问题

## 快速开始

1. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```
2. 配置API密钥（AI功能需配置Qwen或Gemini的API密钥，推荐优先Qwen）
   - Windows PowerShell:
     ```powershell
     $env:QWEN_API_KEY="您的Qwen API密钥"
     $env:GEMINI_API_KEY="您的Gemini API密钥"
     ```
   - Windows CMD:
     ```cmd
     set QWEN_API_KEY=您的Qwen API密钥
     set GEMINI_API_KEY=您的Gemini API密钥
     ```
   - 或编辑`config/default.yaml`:
     ```yaml
     ai:
       qwen_api_key: "您的Qwen API密钥"
       gemini_api_key: "您的Gemini API密钥"
     ```
3. 测试API密钥有效性（推荐）
   ```bash
   python test_api_key.py --model qwen
   python test_api_key.py --model gemini
   ```
4. 执行清理
   ```bash
   python app.py scan --paths C:\Users\你的用户名\Downloads
   python app.py clean --scan-id 1
   ```
5. 使用AI智能规划（实验性）
   ```bash
   python app_new.py ai-plan --goal "清理C盘，释放空间"
   python app_new.py ai-plan --model gemini --goal "清理D盘"
   ```

## 命令行参数说明

- `--model`：指定AI模型（qwen/gemini），默认优先qwen
- `--goal`：清理目标描述（默认：清理C盘，释放磁盘空间）
- `--keep-days`：保留多少天内的文件（默认30天）
- `--paths`：要分析的路径，多个路径用英文逗号分隔，默认C盘根目录
- `--no-backup`：清理时不创建备份（默认创建备份）

## AI清理流程与用户交互

- 用户通过`ai-plan`命令输入清理目标，系统自动调用Qwen（默认）或Gemini生成详细清理计划。
- 计划生成后，系统会展示每一步操作，用户需确认后才会执行实际清理，确保安全。
- 支持自定义扫描路径、排除规则和保留天数，提升灵活性。
- 所有清理操作默认创建备份，用户可随时还原。
- **AI规划会自动适配本机下载目录，避免路径不存在问题。**

## 常见错误及排查建议

- **网络连接失败**：请确保本机网络可访问阿里云（Qwen）或Google（Gemini）API服务。
- **API密钥无效**：请检查API密钥是否正确填写、未过期，建议用`python test_api_key.py --model qwen`或`--model gemini`测试。
- **未配置API密钥**：请在环境变量或config/default.yaml中设置至少一个API密钥。
- **模型不可用**：如Qwen不可用会自动切换Gemini，建议优先配置Qwen。
- **API调用失败**：请查看日志详细错误信息，常见原因包括密钥错误、网络问题、配额限制等。

## 注意事项
- Qwen需能访问阿里云服务，Gemini需能访问Google服务
- API密钥为敏感信息，请妥善保管
- 若一个模型无法生成有效计划，可切换到另一个模型（如加`--model gemini`）
- 详细日志可帮助定位问题
- AI清理计划每一步均需用户确认，避免误删重要文件

如遇问题请优先检查API密钥和网络环境，更多信息见日志和test_api_key.py输出。

## 目录结构

```
├── app.py                # 主程序入口
├── app_new.py            # 新版AI规划入口
├── config/
│   ├── default.yaml      # 默认配置
├── data/
│   ├── models.py         # 数据模型
├── services/
│   ├── ai_planner.py     # AI规划服务
│   ├── logger.py         # 日志服务
├── test_api_key.py       # API密钥测试脚本
├── README.md
├── README_AI_PLAN.md     # AI规划功能详细说明
└── requirements.txt
```

## 依赖
- Python 3.8+
- requests
- loguru
- google-generativeai>=0.5.0（仅Gemini模型需要）

## 贡献与反馈
欢迎提交issue或PR改进本项目。