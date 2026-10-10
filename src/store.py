"""JSON 文件存储层 — 原子写入 + 统一读写接口"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional


def read_json(path: Path) -> dict:
    """读取 JSON 文件，不存在则返回空 dict"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict | list) -> None:
    """原子写入 JSON：先写临时文件，再 rename"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".json", dir=str(path.parent), prefix=".tmp_"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        # Windows 下 rename 需要目标不存在
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def read_json_or_default(path: Path, default: dict | list) -> dict | list:
    """读取 JSON，不存在时返回默认值并写入"""
    if not path.exists():
        write_json(path, default)
        return default
    return read_json(path)


def file_exists(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0
