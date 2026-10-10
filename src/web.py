"""EStudio Web UI — FastAPI + SSE 流式聊天 + CLI 工具流"""

import asyncio
import json
import re
import webbrowser
from datetime import datetime
from typing import AsyncIterator

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse

from .curriculum import (
    get_active_subject,
    load_curriculum,
    load_subjects,
    switch_subject,
)
from .data_models import NodeStatus
from .knowledge import (
    get_due_reviews,
    load_knowledge,
    load_pain_points,
    load_review_queue,
)
from .session import Session
from .store import read_json
from .config import ROOT_DIR, sessions_dir


app = FastAPI(title="EStudio", version="0.1")

# 全局会话引用（简化，单用户够用）
_current_session: Session | None = None


# ── 静态文件 ──────────────────────────────────

STATIC_DIR = ROOT_DIR / "src" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


# ── API: 状态 ─────────────────────────────────


@app.get("/api/status")
def api_status():
    """获取当前学习状态"""
    subject = get_active_subject()
    if not subject:
        return {"error": "没有活跃主题"}

    curriculum = load_curriculum(subject.id)
    if not curriculum:
        return {
            "subject": {"id": subject.id, "name": subject.name},
            "curriculum": None,
        }

    progress = curriculum.progress_summary()

    # 找当前章节
    current_ch = None
    if curriculum.current_node:
        current_ch = curriculum.get_node(curriculum.current_node)
    if not current_ch:
        current_ch = curriculum.get_next_pending()

    # 复习队列 / 困惑点 / 薄弱点
    due_reviews = get_due_reviews(subject.id)
    pain_points = [pp for pp in load_pain_points(subject.id) if not pp.resolved]
    knowledge = load_knowledge(subject.id)

    return {
        "subject": {
            "id": subject.id,
            "name": subject.name,
            "status": subject.status.value if hasattr(subject.status, 'value') else str(subject.status),
        },
        "progress": progress,
        "current_chapter": {
            "id": current_ch.id,
            "title": current_ch.title,
            "status": current_ch.status.value if hasattr(current_ch.status, 'value') else str(current_ch.status),
            "mastery": current_ch.mastery,
            "struggles": current_ch.struggles,
            "last_position": current_ch.last_position,
        } if current_ch else None,
        "modules": [
            {
                "id": m.id,
                "title": m.title,
                "status": m.status.value if hasattr(m.status, 'value') else str(m.status),
                "chapters": [
                    {
                        "id": ch.id,
                        "title": ch.title,
                        "status": ch.status.value if hasattr(ch.status, 'value') else str(ch.status),
                        "mastery": ch.mastery,
                        "struggles": ch.struggles,
                    }
                    for ch in m.chapters
                ],
            }
            for m in curriculum.modules
        ],
        "due_reviews": [
            {
                "chapter_id": r.chapter_id,
                "title": r.title,
                "next_review": r.next_review,
                "mastery": r.mastery_at_completion,
            }
            for r in due_reviews
        ],
        "pain_points": [
            {
                "concept": pp.concept,
                "utterance": pp.user_utterance,
                "count": pp.occurrence_count,
                "triggered_at": pp.triggered_at,
            }
            for pp in pain_points
        ],
        "weak_points": [
            {"concept": w.concept, "severity": w.severity, "suggested_action": w.suggested_action}
            for w in knowledge.weak_points
        ],
    }


@app.get("/api/subjects")
def api_subjects():
    """列出所有主题"""
    index = load_subjects()
    return {
        "active": index.active_subject,
        "subjects": [
            {
                "id": s.id,
                "name": s.name,
                "status": str(s.status),
                "progress": {
                    "total": s.progress.total_chapters,
                    "completed": s.progress.completed,
                } if s.progress else None,
            }
            for s in index.subjects
        ],
    }


@app.post("/api/subjects/switch/{subject_id}")
def api_switch(subject_id: str):
    try:
        entry = switch_subject(subject_id)
        return {"ok": True, "name": entry.name}
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── API: 会话历史 ─────────────────────────────


def _chapter_title_map(subject_id: str) -> dict:
    """chapter_id → 章节标题"""
    curriculum = load_curriculum(subject_id)
    if not curriculum:
        return {}
    return {ch.id: ch.title for ch in curriculum.all_chapters()}


@app.get("/api/sessions")
def api_sessions():
    """列出当前主题的所有会话存档"""
    subject = get_active_subject()
    if not subject:
        return {"sessions": []}

    titles = _chapter_title_map(subject.id)
    sessions = []
    for f in sorted(
        sessions_dir(subject.id).glob("*.json"),
        key=lambda p: p.name,
        reverse=True,
    ):
        data = read_json(f)
        if not data:
            continue

        preview = None
        conv = data.get("conversation", [])
        for m in conv:
            if m.get("role") == "user":
                preview = m.get("content", "")[:80]
                break

        sessions.append({
            "id": data.get("session_id", f.stem),
            "chapter_id": data.get("chapter_id", ""),
            "chapter_title": titles.get(data.get("chapter_id"), data.get("chapter_id", "")),
            "started_at": data.get("started_at"),
            "ended_at": data.get("ended_at"),
            "status": data.get("status", "unknown"),
            "message_count": data.get("message_count", 0),
            "preview": preview,
        })

    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
def api_session_detail(session_id: str):
    """查看一次会话的完整对话记录"""
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", session_id):
        raise HTTPException(400, "非法会话 ID")

    subject = get_active_subject()
    if not subject:
        raise HTTPException(404, "没有活跃主题")

    path = sessions_dir(subject.id) / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "会话不存在")

    data = read_json(path)
    titles = _chapter_title_map(subject.id)
    data["chapter_title"] = titles.get(data.get("chapter_id"), data.get("chapter_id", ""))
    return data


# ── API: 学习会话 ─────────────────────────────


@app.post("/api/learn/start")
def api_learn_start(data: dict = None):
    """开始一个新的学习会话"""
    global _current_session

    subject = get_active_subject()
    if not subject:
        raise HTTPException(400, "没有活跃主题")

    curriculum = load_curriculum(subject.id)
    if not curriculum:
        raise HTTPException(400, "没有课程大纲")

    # 确定学哪个章节
    chapter_id = (data or {}).get("chapter_id")
    if chapter_id:
        chapter = curriculum.get_node(chapter_id)
        if not chapter:
            raise HTTPException(404, f"章节 {chapter_id} 不存在")
    else:
        chapter = curriculum.get_next_pending()
        if not chapter:
            raise HTTPException(400, "所有章节已完成")

    _current_session = Session(subject, chapter)
    greeting = _current_session.start()
    return {"ok": True, "greeting": greeting, "chapter": {"id": chapter.id, "title": chapter.title}}


# ── 工具流：命令提案 → 门控 → 执行 ─────────────────
# 单用户简化：一次只允许一个待决定的命令提案
_pending_tool: dict | None = None


async def _await_tool_decision(timeout: float = 120.0) -> str | None:
    """等待用户对命令提案的决定；返回 approve/deny，None 表示超时"""
    global _pending_tool
    ev = asyncio.Event()
    holder = {"event": ev, "decision": None}
    _pending_tool = holder
    try:
        await asyncio.wait_for(ev.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    _pending_tool = None
    return holder["decision"]


async def _run_command_stream(cmd: str, cwd) -> AsyncIterator[dict]:
    """在受限目录执行命令，产出 tool_stream / tool_end 事件"""
    from .executor import execute

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def on_chunk(stream: str, text: str):
        loop.call_soon_threadsafe(q.put_nowait, (stream, text))

    async def runner():
        try:
            code, timed_out = await asyncio.to_thread(execute, cmd, cwd, on_chunk)
        except Exception as e:
            loop.call_soon_threadsafe(q.put_nowait, ("stderr", f"\n[执行器错误] {e}\n"))
            code, timed_out = -1, False
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)
        return code, timed_out

    task = asyncio.ensure_future(runner())
    collected: list[str] = []
    while True:
        item = await q.get()
        if item is None:
            break
        stream, text = item
        collected.append(text)
        yield {"type": "tool_stream", "stream": stream, "chunk": text}
    code, timed_out = await task
    yield {
        "type": "tool_end",
        "exit_code": code,
        "timed_out": timed_out,
        "output": "".join(collected)[:4000],
    }


async def _chat_stream_loop(session: Session, user_input: str) -> AsyncIterator[dict]:
    """带命令工具环的聊天流（Web 专用）

    事件类型: thinking / content / tool_propose / tool_start /
              tool_stream / tool_end / tool_denied
    """
    from .executor import CMD_FENCE, evaluate_command, parse_command_block, resolve_cwd

    session.append_user_message(user_input)

    FENCE = "```" + CMD_FENCE

    while True:
        # ── 一轮 AI 回复：流式输出，途中识别命令块 ──
        # 注意：fence 会被 SSE 拆到多个 chunk，必须跨 chunk 累积检测
        turn_text = ""
        run_buf = ""
        in_block = False
        block_buf = ""
        proposed = None

        for event in session.ai.chat_stream(
            messages=session.conversation,
            system_prompt=session.build_system_prompt(enable_tools=True),
            include_reasoning=True,
        ):
            if event["type"] != "content":
                yield event
                continue

            run_buf += event["content"]

            while run_buf:
                if not in_block:
                    # 扣下尾部可能是 fence 前缀的部分，防误发
                    hold_len = 0
                    for i in range(1, len(FENCE) + 1):
                        if run_buf.endswith(FENCE[:i]):
                            hold_len = i
                    safe = run_buf[: len(run_buf) - hold_len] if hold_len else run_buf
                    hold = run_buf[len(safe):]

                    idx = safe.find(FENCE)
                    if idx < 0:
                        if safe:
                            turn_text += safe
                            yield {"type": "content", "content": safe}
                        run_buf = hold
                        break

                    # 命中 opening fence
                    before = safe[:idx]
                    rest = safe[idx + len(FENCE):]
                    if before:
                        turn_text += before
                        yield {"type": "content", "content": before}
                    in_block = True
                    run_buf = rest + hold  # hold 可能是闭合 fence 的碎片，不能丢
                    continue  # 同一 chunk 内继续找闭合

                # 块内：跨 chunk 累积，找闭合 fence（同样可能被拆）
                block_buf += run_buf
                run_buf = ""
                end = block_buf.find("```")
                if end < 0:
                    break
                tail = block_buf[end + 3:]
                block_buf = block_buf[:end]
                in_block = False
                proposed = parse_command_block(block_buf)
                raw_block = block_buf
                block_buf = ""
                if proposed is None:
                    # 解析失败：整个块按普通文本输出，继续流
                    raw = FENCE + raw_block + "```" + tail
                    turn_text += raw
                    yield {"type": "content", "content": raw}
                    continue
                turn_text += tail
                if tail:
                    yield {"type": "content", "content": tail}
                break

            if proposed is not None:
                break

        # 流结束兜底：残留缓冲区 / 半截命令块按文本输出
        if run_buf:
            turn_text += run_buf
            yield {"type": "content", "content": run_buf}
        if in_block:
            dangling = FENCE + block_buf
            turn_text += dangling
            yield {"type": "content", "content": dangling}
            proposed = None

        # 本轮可见文本归档
        if turn_text:
            session.append_assistant_message(turn_text)

        if proposed is None:
            break

        cmd = str(proposed.get("cmd", "")).strip()
        cwd_rel = str(proposed.get("cwd", "")).strip() or "."
        reason = str(proposed.get("reason", "")).strip()[:200]
        if not cmd:
            break

        verdict = evaluate_command(cmd)
        tool_entry = {
            "cmd": cmd,
            "cwd": cwd_rel,
            "reason": reason,
            "verdict": verdict["verdict"],
            "dangerous": verdict["dangerous"],
            "decision": None,
            "exit_code": None,
            "at": datetime.now().isoformat(),
        }

        yield {
            "type": "tool_propose",
            "cmd": cmd,
            "cwd": cwd_rel,
            "reason": reason,
            "verdict": verdict["verdict"],
            "dangerous": verdict["dangerous"],
            "note": verdict["reason"],
        }

        # ── 门控：deny 拦截 / approve 等用户 / auto 放行 ──
        if verdict["verdict"] == "deny":
            decision = "deny"
        elif verdict["verdict"] == "approve":
            decision = await _await_tool_decision()
        else:
            decision = "approve"
        tool_entry["decision"] = decision or "timeout"
        session.tool_log.append(tool_entry)

        if decision != "approve":
            why = (
                verdict["reason"] if verdict["verdict"] == "deny"
                else ("用户拒绝" if decision else "等待批准超时")
            )
            yield {"type": "tool_denied", "reason": why}
            session.conversation.append({
                "role": "user",
                "content": f"[系统] 命令未执行（{why}）：{cmd}\n请用文字继续讲解，不要再尝试执行该命令。",
            })
            session.save_checkpoint()
            continue

        # ── 工作目录约束 ──
        cwd = resolve_cwd(ROOT_DIR, cwd_rel)
        if cwd is None:
            yield {"type": "tool_denied", "reason": "工作目录越界（只能访问项目根目录内）"}
            session.conversation.append({
                "role": "user",
                "content": "[系统] 命令未执行（工作目录越界，只能访问项目根目录内）。请用文字继续。",
            })
            session.save_checkpoint()
            continue

        # ── 执行 ──
        yield {"type": "tool_start", "cmd": cmd, "cwd": cwd_rel}
        exit_code, timed_out = None, False
        async for ev in _run_command_stream(cmd, cwd):
            yield ev
            if ev["type"] == "tool_end":
                exit_code = ev["exit_code"]
                timed_out = ev["timed_out"]
                output = ev["output"]
        tool_entry["exit_code"] = exit_code

        result_text = (
            f"命令: {cmd}\n"
            f"工作目录: {cwd_rel}\n"
            f"退出码: {'超时' if timed_out else exit_code}\n"
            f"输出（截取前 4000 字符）:\n{output or '(无输出)'}\n"
            f"请基于真实结果继续讲解。"
        )
        session.conversation.append({
            "role": "user",
            "content": f"[系统命令执行结果]\n{result_text}",
        })
        session.save_checkpoint()
        # 回到循环顶部：AI 基于命令结果继续回复

    session.save_checkpoint()


@app.post("/api/learn/chat")
async def api_learn_chat(request: Request):
    """流式聊天（带命令工具环）"""
    global _current_session

    if not _current_session:
        raise HTTPException(400, "没有活跃的会话，请先开始学习")

    data = await request.json()
    user_input = data.get("message", "")

    if not user_input.strip():
        raise HTTPException(400, "消息不能为空")

    # 特殊命令
    if user_input.strip() in ("结束", "quit", "exit"):
        return JSONResponse({"type": "end", "content": None})

    session = _current_session

    async def generate():
        try:
            async for event in _chat_stream_loop(session, user_input.strip()):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'content', 'content': f'\\n[系统错误: {e}]'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/learn/tool/decide")
async def api_tool_decide(request: Request):
    """用户对命令提案做决定（approve / deny）"""
    global _pending_tool

    if not _pending_tool:
        raise HTTPException(400, "没有待决定的命令")

    data = await request.json()
    decision = data.get("decision")
    if decision not in ("approve", "deny"):
        raise HTTPException(400, "decision 必须是 approve 或 deny")

    _pending_tool["decision"] = decision
    _pending_tool["event"].set()
    return {"ok": True}


@app.post("/api/learn/end")
def api_learn_end():
    """结束当前会话"""
    global _current_session

    if not _current_session:
        raise HTTPException(400, "没有活跃的会话")

    chapter = _current_session.chapter
    result = _current_session.end()

    # 重新加载课程树，拿到最新的章节状态
    curriculum = load_curriculum(_current_session.subject.id)
    completed = False
    if curriculum:
        node = curriculum.get_node(chapter.id)
        completed = node is not None and node.status == NodeStatus.COMPLETED

    note_file = getattr(chapter, "notes_file", None)

    _current_session = None
    return {
        "ok": True,
        "result": result,
        "chapter_id": chapter.id,
        "mastery": chapter.mastery,
        "completed": completed,
        "note_file": note_file,
    }


@app.get("/api/learn/status")
def api_learn_status():
    """当前会话状态"""
    if not _current_session:
        return {"active": False}

    ch = _current_session.chapter
    return {
        "active": True,
        "chapter": ch.title,
        "message_count": len(_current_session.conversation) // 2,
        "last_position": ch.last_position,
        "struggles": ch.struggles,
    }


# ── HTML 页面 ─────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        content = html_path.read_text(encoding="utf-8")
        # 注入 BASE_URL 用于相对路径
        return content
    return "<h1>Static files not found. Run: python -m src.main web</h1>"


# ── 启动 ─────────────────────────────────────


def start_web(host: str = "127.0.0.1", port: int = 7890, open_browser: bool = True):
    """启动 Web 服务"""
    import uvicorn

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(app, host=host, port=port, log_level="info")
