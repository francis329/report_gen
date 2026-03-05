import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
REPORTS_DIR = BASE_DIR / "reports"

# 确保目录存在
UPLOAD_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# 文件大小限制：10MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 允许的文件类型
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# AI 模型配置
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_MODEL = "qwen3.5-plus"  # 阿里云百炼有效模型 ID
