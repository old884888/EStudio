"""命令执行层 — CLI 命令的协议解析、安全评估与受限执行（雷一）

协议：AI 在回复中需要执行命令时，整条回复只输出以下围栏块：

```estudio-cmd
{"cmd": "要执行的命令", "cwd": "可选：相对项目根目录", "reason": "一句话理由"}
```

安全三档：
  deny    → 直接拦截（提权/交互式/远程等），不执行
  approve → 危险操作或不在白名单，必须用户批准
  auto    → 白名单只读/运行类命令，自动放行
"""

import json
import re
import subprocess
import threading
from pathlib import Path

CMD_FENCE = "estudio-cmd"

# ── 安全评估规则 ─────────────────────────────────
# 命中即拦截（优先级最高，不管在不在白名单）
DENY_PATTERNS = [
    (r"\bsudo\b|\brunas\b|elevate", "提权操作"),
    (r"^(python|py|ipython|node|npm|cmd|powershell|pwsh|bash|sh|zsh)\s*$", "交互式终端"),
    (r"^(ssh|scp|sftp|ftp|telnet)\b", "远程操作"),
    (r"\bcertutil\b|\bnetsh\b|\bregedit\b", "系统级工具"),
]

# 命中即需要人工批准（UI 标红警示）
DANGEROUS_PATTERNS = [
    (r"rm\s+(-\w*r\w*)+", "递归删除"),
    (r"(rmdir|rd)\s+/s", "递归删除目录"),
    (r"del\s+/[sqf]", "强制删除"),
    (r"\bformat\s", "格式化磁盘"),
    (r"\bdiskpart\b|\bmkfs\b", "磁盘工具"),
    (r"\bdd\s+if=", "裸写磁盘"),
    (r"\bshutdown\b|\breboot\b", "关机/重启"),
    (r"taskkill\s+/f", "强制杀进程"),
    (r"\breg\s+(add|delete)", "修改注册表"),
    (r"git\s+(push|reset|clean|checkout)\b", "git 破坏性操作"),
    (r"pip\s+uninstall", "卸载包"),
]

# 命中即自动放行（只读/运行类）
AUTO_PATTERNS = [
    (r"^(dir|ls|type|cat|more|head|tail|tree|pwd|where|which|echo|findstr|grep)\b", "查看类"),
    (r"^(python|py)\s+\S", "运行脚本"),
    (r"^pytest\b", "测试"),
    (r"^git\s+(status|log|diff|show|branch)\b", "git 只读"),
    (r"^(pip|npm)\s+(list|show|view|ls|index)\b", "包查询"),
    (r"^(node)\s+\S", "node 脚本"),
    (r"^(npm)\s+run\b", "npm 脚本"),
]


def evaluate_command(cmd: str) -> dict:
    """评估一条命令的安全性，返回 {verdict, dangerous, reason}"""
    stripped = cmd.strip()

    for pattern, why in DENY_PATTERNS:
        if re.search(pattern, stripped, re.I):
            return {"verdict": "deny", "dangerous": True, "reason": f"拦截：{why}"}

    for pattern, why in DANGEROUS_PATTERNS:
        if re.search(pattern, stripped, re.I):
            return {"verdict": "approve", "dangerous": True,
                    "reason": f"危险操作（{why}），需要批准"}

    for pattern, why in AUTO_PATTERNS:
        if re.search(pattern, stripped, re.I):
            return {"verdict": "auto", "dangerous": False,
                    "reason": f"白名单自动放行（{why}）"}

    return {"verdict": "approve", "dangerous": False, "reason": "不在白名单内，需要批准"}


def parse_command_block(raw: str) -> dict | None:
    """解析命令块内的 JSON，返回 {"cmd", "cwd", "reason"} 或 None"""
    text = raw.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 允许 JSON 前后有杂质，取第一个 {…}
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or not isinstance(data.get("cmd"), str):
        return None
    return data


def resolve_cwd(root: Path, cwd: str) -> Path | None:
    """把 AI 给的工作目录解析到项目根目录内；越界返回 None"""
    try:
        p = (root / cwd).resolve()
    except OSError:
        return None
    root_r = root.resolve()
    if p == root_r or root_r in p.parents:
        return p
    return None


def execute(
    cmd: str,
    cwd: Path,
    on_chunk,
    timeout: float = 60.0,
    max_chars: int = 20000,
) -> tuple[int, bool]:
    """同步执行命令（在线程中调用）。on_chunk(stream, text) 实时回调。

    stream: "stdout" | "stderr"。返回 (exit_code, timed_out)；
    超时返回 (-1, True)，命令被 kill。
    """
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    counters = {"stdout": 0, "stderr": 0}

    def pump(stream, name: str) -> None:
        # 读到 EOF 为止；超过 max_chars 后继续排空但不再转发
        for line in iter(stream.readline, ""):
            used = counters[name]
            if used >= max_chars:
                continue
            piece = line[: max_chars - used]
            counters[name] += len(piece)
            on_chunk(name, piece)

    t_out = threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True)
    t_err = threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True)
    t_out.start()
    t_err.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        timed_out = True
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    t_out.join(timeout=3)
    t_err.join(timeout=3)
    if timed_out:
        on_chunk("stderr", f"\n[命令超时（>{timeout:g}s），已强制终止]\n")
    return (proc.returncode if not timed_out else -1), timed_out
