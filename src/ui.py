"""CLI 界面 — 基于 rich 的终端 UI"""

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.markdown import Markdown
from rich.rule import Rule

from .data_models import (
    Chapter,
    Curriculum,
    NodeStatus,
    PainPoint,
    ReviewEntry,
    SubjectEntry,
    SubjectsIndex,
    SubjectStatus,
)

# Windows PowerShell 默认 GBK 编码不支持 emoji，
# legacy_windows=False 强制 rich 用现代渲染模式（UTF-8）
console = Console(legacy_windows=False)

# ── 调色板：全部避开纯蓝 ──────────────────────

THEME = {
    "primary": "cyan",        # 替代纯蓝，柔和
    "success": "green",
    "warning": "yellow",
    "danger": "red",
    "accent": "magenta",
    "dim": "dim",
    "bold": "bold",
    "title": "bold white",
}

# ── 状态图标（纯文本，不用 emoji，避免兼容问题）──

STATUS_ICON = {
    NodeStatus.NOT_STARTED: "[ ]",
    NodeStatus.IN_PROGRESS: "[>]",
    NodeStatus.COMPLETED: "[x]",
    NodeStatus.PAUSED: "[||]",
}


def mastery_bar(mastery: float | None, width: int = 10) -> str:
    """掌握度进度条"""
    if mastery is None:
        return "-" * width
    filled = int(mastery * width)
    return "#" * filled + "." * (width - filled)


def mastery_color(mastery: float | None) -> str:
    """掌握度对应的颜色"""
    if mastery is None:
        return THEME["dim"]
    if mastery >= 0.8:
        return THEME["success"]
    if mastery >= 0.5:
        return THEME["warning"]
    return THEME["danger"]


# ── 启动画面 ───────────────────────────────────


def show_banner() -> None:
    console.print()
    console.print("EStudio v0.1 - 有状态的结构化学习引擎", style="bold cyan")
    console.print()


# ── 主题视图 ───────────────────────────────────


def show_subjects(index: SubjectsIndex) -> None:
    """显示所有学习主题"""
    table = Table(title="学习主题", border_style=THEME["primary"])
    table.add_column("")
    table.add_column("主题名称")
    table.add_column("状态")
    table.add_column("进度")

    for s in index.subjects:
        is_active = s.id == index.active_subject
        marker = ">" if is_active else " "
        status_text = {
            SubjectStatus.NOT_STARTED: "未开始",
            SubjectStatus.IN_PROGRESS: "学习中",
            SubjectStatus.COMPLETED: "已完成",
        }.get(s.status, "?")

        if s.progress and s.progress.total_chapters > 0:
            pct = round(s.progress.completed / s.progress.total_chapters * 100, 1)
            progress_str = f"{s.progress.completed}/{s.progress.total_chapters} ({pct}%)"
        else:
            progress_str = "-"

        style = f"bold {THEME['primary']}" if is_active else ""
        table.add_row(marker, f"[{style}]{s.name}[/]", status_text, progress_str)

    console.print(table)


# ── 大纲视图 ───────────────────────────────────


def show_curriculum(curriculum: Curriculum, highlight_id: Optional[str] = None) -> None:
    """以树状结构显示课程大纲"""
    progress = curriculum.progress_summary()

    title = Text(
        f"{curriculum.description}  "
        f"({progress['completed']}/{progress['total']}, {progress['percent']}%)",
        style="bold white",
    )

    root = Tree(title)

    for mod in curriculum.modules:
        mod_icon = STATUS_ICON.get(mod.status, "[ ]")
        mod_style = "bold"
        if mod.status == NodeStatus.IN_PROGRESS:
            mod_style = f"bold {THEME['warning']}"
        elif mod.status == NodeStatus.COMPLETED:
            mod_style = f"bold {THEME['success']}"

        mod_text = Text(f"{mod_icon} {mod.title}", style=mod_style)
        mod_node = root.add(mod_text)

        for ch in mod.chapters:
            ch_icon = STATUS_ICON.get(ch.status, "[ ]")
            m_bar = mastery_bar(ch.mastery)
            m_color = mastery_color(ch.mastery)

            ch_style = THEME["dim"]
            if ch.id == highlight_id or ch.id == curriculum.current_node:
                ch_style = f"bold {THEME['primary']}"
            elif ch.status == NodeStatus.IN_PROGRESS:
                ch_style = THEME["warning"]
            elif ch.status == NodeStatus.COMPLETED:
                ch_style = THEME["success"]

            ch_text = Text(f"{ch_icon} {ch.title}  [{m_color}]{m_bar}[/{m_color}]", style=ch_style)

            if ch.struggles:
                ch_text.append(f"  ! {', '.join(ch.struggles)}", style=f"{THEME['danger']} {THEME['dim']}")

            mod_node.add(ch_text)

    console.print(root)
    console.print()


# ── 启动面板 ───────────────────────────────────


def show_startup(
    subject: SubjectEntry,
    curriculum: Optional[Curriculum],
    current_chapter: Optional[Chapter],
    due_reviews: list[ReviewEntry],
    pain_points: list[PainPoint],
) -> None:
    """显示启动面板"""
    console.print()

    if curriculum is None:
        console.print(f"[{THEME['warning']}]还没有课程大纲，请先用 'new' 和 'outline' 创建[/]")
        return

    # 进度概览
    progress = curriculum.progress_summary()
    console.print(Panel(
        f"[bold]{subject.name}[/bold]\n"
        f"进度: {progress['completed']}/{progress['total']} 章 ({progress['percent']}%)\n"
        f"学习中: {progress['in_progress']} 章",
        title="学习概览",
        border_style=THEME["primary"],
    ))

    # 当前进度
    if current_chapter:
        struggles_text = ""
        if current_chapter.struggles:
            struggles_text = f"\n卡住的点: {', '.join(current_chapter.struggles)}"
        m_color = mastery_color(current_chapter.mastery)
        m_bar = mastery_bar(current_chapter.mastery)
        mastery_val = f"{current_chapter.mastery:.0%}" if current_chapter.mastery is not None else "-"
        console.print(Panel(
            f"[bold {THEME['warning']}]> {current_chapter.title}[/]\n"
            f"掌握度: [{m_color}]{m_bar}[/{m_color}] {mastery_val}"
            f"{struggles_text}\n"
            f"上次进度: {current_chapter.last_position or '(新章节，未开始)'}",
            title="当前进度",
            border_style=THEME["warning"] if current_chapter.status == NodeStatus.IN_PROGRESS else THEME["success"],
        ))

    # 待复习
    if due_reviews:
        review_list = "\n".join(
            f"  - {r.title} ({r.mastery_at_completion:.0%})"
            for r in due_reviews[:5]
        )
        console.print(Panel(review_list, title="待复习", border_style=THEME["accent"]))

    # 困惑
    unresolved = [pp for pp in pain_points if not pp.resolved]
    if unresolved:
        pp_list = "\n".join(
            f"  - {pp.concept} (出现{pp.occurrence_count}次)"
            for pp in unresolved[:3]
        )
        console.print(Panel(pp_list, title="未解决的困惑", border_style=THEME["danger"]))

    console.print()


# ── 对话界面 ───────────────────────────────────


def chat_loop(session) -> None:
    """对话循环 — 极简风格"""
    console.print()

    # 顶栏
    console.print(Rule(
        f"[bold]{session.chapter.title}[/bold]  [dim]|  输入 '结束' 保存  |  '状态' 查看进度  |  '复习' 做练习[/dim]",
        style=THEME["primary"],
    ))
    console.print()

    # AI 问候
    greeting = session.start()
    console.print(Panel(greeting, border_style=THEME["primary"]))
    console.print()

    while True:
        try:
            user_input = console.input("[bold]你 > [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[{THEME['warning']}]正在保存...[/]")
            break

        if not user_input:
            continue

        if user_input in ("结束", "quit", "exit", "q", "/quit", "/exit"):
            break
        if user_input in ("状态", "status", "/status"):
            _show_status(session)
            continue
        if user_input in ("帮助", "help", "/help"):
            console.print(f"[{THEME['dim']}]命令: 结束=保存退出 | 状态=查看进度 | 复习=做练习 | 帮助=显示此信息[/]")
            continue
        if user_input in ("复习", "review"):
            _quick_review(session)
            continue

        console.print()

        # AI 回复 —— 流式输出
        from rich.live import Live
        from rich.text import Text

        buffer = Text("")
        # 初始渲染一个空面板，防止 Live resize 时内容缺失
        with Live(
            Panel(buffer, border_style=THEME["primary"]),
            console=console,
            refresh_per_second=20,
            transient=False,
            vertical_overflow="visible",
        ) as live:
            for chunk in session.chat_stream(user_input):
                buffer.append(chunk)
                live.update(Panel(buffer, border_style=THEME["primary"]))

        console.print()

    # 结束
    result = session.end()
    console.print()
    console.print(Panel(result, title="会话总结", border_style=THEME["success"]))


def _show_status(session) -> None:
    """显示当前会话状态"""
    ch = session.chapter
    console.print(f"\n[bold]当前位置:[/] {ch.title}")
    console.print(f"[bold]对话轮数:[/] {len(session.conversation) // 2}")
    console.print(f"[bold]上次进度:[/] {ch.last_position or '无'}")
    if ch.struggles:
        console.print(f"[bold]卡住的地方:[/] {', '.join(ch.struggles)}")
    console.print()


def _quick_review(session) -> None:
    """快速出题"""
    ai = session.ai
    response = ai.chat(
        messages=[{
            "role": "user",
            "content": (
                f"请针对「{session.chapter.title}」出一个简短的练习题。"
                "用户正在学习这个章节，请出 1 道能检验核心概念理解的题。"
                "不要出太偏的题，聚焦最重要的概念。"
            ),
        }],
        system_prompt="你是出题老师。只出 1 道题，简洁。",
        temperature=0.5,
    )
    console.print(Panel(response, title="快速练习", border_style=THEME["accent"]))
    console.print()


# ── 确认框 ───────────────────────────────────


def confirm(msg: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    ans = input(msg + suffix).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes", "是")
