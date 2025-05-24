# AI规划功能使用指南

## 多模型支持

本工具支持多种AI大模型生成清理计划，当前**默认优先使用Qwen（通义千问）**，如未配置Qwen则自动切换到Gemini。

- **Qwen** - 阿里云通义千问大模型（默认推荐）
- **Gemini** - Google大语言模型

> 目前已移除对文心一言的支持，相关配置和说明已废弃。

您只需配置Qwen或Gemini的API密钥即可，无需同时配置。

## 功能介绍

- 自动分析磁盘空间，生成清理建议
- 支持自定义清理目标和参数
- 支持多模型切换，Qwen优先
- **自动适配本机下载目录**：AI规划会自动检测本机的下载目录（如 `C:\Users\你的用户名\Downloads`），不会再出现路径不存在的问题

## 使用示例

### 1. 设置API密钥

#### Windows PowerShell
$env:QWEN_API_KEY="您的Qwen API密钥"
$env:GEMINI_API_KEY="您的Gemini API密钥"

#### Windows CMD
set QWEN_API_KEY=您的Qwen API密钥
set GEMINI_API_KEY=您的Gemini API密钥

#### 配置文件（config/default.yaml）
ai:
  qwen_api_key: "您的Qwen API密钥"
  gemini_api_key: "您的Gemini API密钥"

### 2. 测试API密钥（推荐）
python test_api_key.py --model qwen
python test_api_key.py --model gemini

### 3. 运行AI规划功能
python app_new.py ai-plan --goal "清理C盘，释放空间"
python app_new.py ai-plan --model gemini --goal "清理D盘"

## 参数说明
- `--model`: 指定AI模型（qwen/gemini），默认优先qwen
- `--goal`: 清理目标描述（默认：清理C盘，释放磁盘空间）
- `--keep-days`: 保留多少天内的文件（默认30天）
- `--paths`: 要分析的路径，多个路径用英文逗号分隔，默认C盘根目录

## AI清理计划用户交互与安全性

- 用户通过`ai-plan`命令输入清理目标，系统自动调用Qwen（默认）或Gemini生成详细清理计划。
- 生成的计划会逐步展示每一步操作，用户需确认后才会执行实际清理，避免误删重要文件。
- 所有清理操作默认创建备份，用户可随时还原，保障数据安全。
- 支持自定义扫描路径、排除规则和保留天数，提升灵活性。
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