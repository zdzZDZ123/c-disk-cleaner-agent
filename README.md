# C Disk Cleaner

An intelligent Windows C drive cleaning tool with AI-assisted analysis, multi-turn dialogue, automatic backup, and scheduled cleaning.

## Features (2024)

- 🤖 **AI-Powered Multi-Model Planning**
  - Supports both Qwen (Alibaba) and Google Gemini AI models
  - Multi-turn natural language dialogue for cleaning plan optimization
  - Automatic model switching (VPN/region aware)
  - Each file is analyzed and marked as `safe` (auto-clean), `confirm` (manual), or `forbid` (never delete)
  - AI auto-adapts to local directories (Downloads, Desktop, etc.)

- 🔍 **Smart Scanning & Analysis**
  - Auto-discover system junk, temp, browser cache, IM/download/game caches
  - Large file and duplicate file detection and grouping
  - Custom scan/exclude paths, retention days

- 🧹 **Safe Cleaning & Backup**
  - Automatic backup before cleaning, one-click restore
  - System temp, browser cache, downloads, recycle bin cleaning
  - Custom cleaning rules via `config/rules.yaml`

- 📊 **Reports & Statistics**
  - Before/after space comparison, auto space freed report
  - Detailed cleaning reports, exportable history

- ⏰ **Automation & Scheduling**
  - Scheduled auto-cleaning (configurable interval, categories)
  - Full/partial automation via CLI

- 🛠️ **Robust CLI & Logging**
  - Rich command-line interface: `scan`, `clean`, `ai-plan`, `restore`, `list-backups`, `list-duplicates`, `schedule`, `rules`
  - Detailed logs and error messages for troubleshooting
  - API key validity test script

## Installation

1. Clone the repository:
```bash
git clone https://github.com/zdzZDZ123/c_disk_cleaner_agent.git
cd c_disk_cleaner_agent
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Configure API keys (Qwen and/or Gemini):
   - In `config/default.yaml` or via environment variables:
     ```bash
     $env:QWEN_API_KEY="your_qwen_api_key"
     $env:GEMINI_API_KEY="your_gemini_api_key"
     ```

## Usage Examples

- Basic usage:
  ```bash
  python app.py
  ```
- AI planning (multi-turn):
  ```bash
  python app.py ai-plan
  ```
- Scan specific path:
  ```bash
  python app.py scan --paths C:\Users\YourName\Downloads
  ```
- Clean with scan ID:
  ```bash
  python app.py clean --scan-id 1
  ```
- List backups/duplicates:
  ```bash
  python app.py list-backups
  python app.py list-duplicates --scan-id 1
  ```
- Schedule auto-clean:
  ```bash
  python app.py schedule --enable --interval 14 --categories temp_files,cache_files
  ```
- Test API keys:
  ```bash
  python test_api_key.py --model qwen
  python test_api_key.py --model gemini
  ```

## AI Planning & Safety
- Users interact with AI via `ai-plan` command, multi-turn dialogue supported
- Each cleaning step requires user confirmation before execution (prevents accidental deletion)
- All cleaning operations create backups by default, one-click restore supported
- AI auto-adapts to your system's actual directories

## Configuration
- API keys: `config/default.yaml` or environment variables
- Cleaning rules: `config/rules.yaml`
- Scheduling: via `schedule` command or config

## Troubleshooting & Quota
- **API Quota Exceeded (429)**: If you see `RESOURCE_EXHAUSTED` or 429 errors, your API quota is used up. Check your Google/Aliyun console for quota/billing, or wait for reset.
- **Network/API Key Issues**: Ensure network access to Aliyun/Google, and API keys are valid (use `test_api_key.py`)
- **Logs**: See `logs/app.log` for detailed error info

## Directory Structure
```
├── app.py                # Main program entry
├── config/
├── data/
├── services/
├── core/
├── test_api_key.py       # API key test script
├── README.md
└── requirements.txt
```

## Dependencies
- Python 3.8+
- requests
- loguru
- google-generativeai>=0.5.0 (for Gemini)

## License
MIT

## Contact
- Project: https://github.com/zdzZDZ123/c_disk_cleaner_agent
- Issues: https://github.com/zdzZDZ123/c_disk_cleaner_agent/issues