"""配置管理：路径、默认值、环境变量"""

import os
import sys
from pathlib import Path

# Windows 终端默认 GBK 不支持 emoji 和中文特殊字符，
# 强制把 stdout/stderr 重配为 UTF-8（Python 3.7+ 支持）
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent

# ── 加载 .env 文件 ────────────────────────────
# 如果用户创建了 .env，自动加载里面的环境变量（不覆盖已有值）
def _load_dotenv():
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

_load_dotenv()

# 数据目录
DATA_DIR = ROOT_DIR / "data"

# Prompt 模板目录
PROMPTS_DIR = ROOT_DIR / "prompts"

# ── 路径工具 ──────────────────────────────────


def subject_dir(subject_id: str) -> Path:
    """返回某个主题的数据目录"""
    d = DATA_DIR / "subjects" / subject_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def subjects_index_path() -> Path:
    """多主题索引文件路径"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "subjects.json"


def curriculum_path(subject_id: str) -> Path:
    return subject_dir(subject_id) / "curriculum.json"


def knowledge_path(subject_id: str) -> Path:
    return subject_dir(subject_id) / "knowledge.json"


def review_queue_path(subject_id: str) -> Path:
    return subject_dir(subject_id) / "review_queue.json"


def pain_points_path(subject_id: str) -> Path:
    return subject_dir(subject_id) / "pain_points.json"


def notes_dir(subject_id: str) -> Path:
    d = subject_dir(subject_id) / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sessions_dir(subject_id: str) -> Path:
    d = subject_dir(subject_id) / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── AI 配置 ────────────────────────────────────

# 从环境变量读取，带默认值
AI_MODEL = os.environ.get("ESTUDIO_MODEL", "deepseek-chat")
AI_PROVIDER = os.environ.get("ESTUDIO_PROVIDER", "deepseek")
AI_MAX_TOKENS = int(os.environ.get("ESTUDIO_MAX_TOKENS", "4096"))
