"""EStudio CLI 入口 — 有状态的结构化学习引擎"""

import sys
from typing import Optional

from .ai_provider import generate_curriculum
from .config import AI_MODEL, AI_PROVIDER
from .curriculum import (
    create_subject,
    get_active_subject,
    init_curriculum,
    load_curriculum,
    load_subjects,
    switch_subject,
    update_subject_progress,
)
from .data_models import (
    Chapter,
    Curriculum,
    NodeStatus,
    SubjectEntry,
    SubjectProgress,
    SubjectStatus,
)
from .knowledge import (
    get_due_reviews,
    load_pain_points,
)
from .session import Session
from .ui import (
    confirm,
    console,
    show_banner,
    show_curriculum,
    show_startup,
    show_subjects,
    chat_loop,
)


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════


def _validate_active_subject() -> tuple[SubjectEntry, Optional[Curriculum]]:
    """验证有活跃主题，加载课程树"""
    subject = get_active_subject()
    if subject is None:
        console.print("[red]没有活跃的学习主题。请先用 'new' 命令创建一个。[/red]")
        return None, None
    curriculum = load_curriculum(subject.id)
    if curriculum is None:
        console.print(f"[yellow]主题「{subject.name}」还没有课程大纲。用 'outline' 命令生成。[/yellow]")
        return subject, None
    return subject, curriculum


def _get_current_chapter(curriculum: Curriculum) -> Optional[Chapter]:
    """获取当前正在学习的章节"""
    if curriculum.current_node:
        return curriculum.get_node(curriculum.current_node)
    return curriculum.get_next_pending()


# ═══════════════════════════════════════════════
# 命令处理
# ═══════════════════════════════════════════════


def cmd_new(args: list[str]) -> None:
    """创建新主题"""
    if not args:
        console.print("用法: estudio new <主题名> [主题ID]")
        return

    name = args[0]
    subject_id = args[1] if len(args) > 1 else name.lower().replace(" ", "-")

    try:
        entry = create_subject(subject_id, name)
        console.print(f"[green]✅ 已创建主题「{name}」(ID: {subject_id})[/green]")
        console.print(f"下一步: estudio outline 生成课程大纲")
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")


def cmd_switch(args: list[str]) -> None:
    """切换主题"""
    if not args:
        console.print("用法: estudio switch <主题ID>")
        index = load_subjects()
        if index.subjects:
            console.print(f"可用主题: {', '.join(s.id for s in index.subjects)}")
        return

    try:
        entry = switch_subject(args[0])
        console.print(f"[green]✅ 已切换到「{entry.name}」[/green]")
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")


def cmd_list(args: list[str]) -> None:
    """列出所有主题"""
    index = load_subjects()
    if not index.subjects:
        console.print("[dim]还没有学习主题。用 'estudio new <主题名>' 创建一个[/dim]")
        return
    show_subjects(index)


def cmd_outline(args: list[str]) -> None:
    """生成课程大纲"""
    subject = get_active_subject()
    if subject is None:
        console.print("[red]请先用 'new' 创建主题[/red]")
        return

    curriculum = load_curriculum(subject.id)
    if curriculum is not None:
        if not confirm("课程大纲已存在，要重新生成吗？"):
            return

    console.print(f"🤖 正在为「{subject.name}」生成课程大纲...")
    outline = generate_curriculum(subject.id if subject.id else subject.name)

    if "modules" not in outline:
        console.print(f"[red]❌ AI 返回的格式有误: {outline}[/red]")
        return

    curriculum = init_curriculum(
        subject.id,
        subject.name,
        outline["modules"],
    )

    # 更新主题状态
    subject.status = SubjectStatus.IN_PROGRESS
    from .curriculum import save_subjects, load_subjects
    index = load_subjects()
    for s in index.subjects:
        if s.id == subject.id:
            s.status = SubjectStatus.IN_PROGRESS
            save_subjects(index)
            break

    console.print(f"[green]✅ 大纲生成完毕！共 {len(curriculum.modules)} 个模块[/green]")
    show_curriculum(curriculum)


def cmd_status(args: list[str]) -> None:
    """查看当前进度"""
    subject, curriculum = _validate_active_subject()
    if subject is None:
        return

    if curriculum is None:
        return

    current_ch = _get_current_chapter(curriculum)
    due_reviews = get_due_reviews(subject.id)
    pain_points = load_pain_points(subject.id)

    show_startup(subject, curriculum, current_ch, due_reviews, pain_points)
    show_curriculum(curriculum, highlight_id=curriculum.current_node)


def cmd_learn(args: list[str]) -> None:
    """开始/继续学习"""
    subject, curriculum = _validate_active_subject()
    if subject is None or curriculum is None:
        return

    # 确定学哪个章节
    if args:
        chapter_id = args[0]
        chapter = curriculum.get_node(chapter_id)
        if chapter is None:
            # 尝试模糊匹配
            for ch in curriculum.all_chapters():
                if args[0].lower() in ch.title.lower() or ch.id.endswith(args[0]):
                    chapter = ch
                    break
            if chapter is None:
                console.print(f"[red]找不到章节: {args[0]}[/red]")
                return
    else:
        chapter = _get_current_chapter(curriculum)
        if chapter is None:
            console.print("[green]🎉 所有章节都已完成！[/green]")
            return

    # 如果该章节已完成，确认是否重学
    if chapter.status == NodeStatus.COMPLETED:
        if not confirm(f"「{chapter.title}」已完成，要重新学习吗？"):
            return

    # 创建并启动会话
    session = Session(subject, chapter)
    chat_loop(session)


def cmd_notes(args: list[str]) -> None:
    """查看笔记"""
    subject, curriculum = _validate_active_subject()
    if subject is None or curriculum is None:
        return

    from .config import notes_dir
    notes_path = notes_dir(subject.id)

    if args:
        # 查看特定章节的笔记
        chapter_id = args[0]
        chapter = curriculum.get_node(chapter_id)
        if chapter is None:
            console.print(f"[red]找不到章节: {chapter_id}[/red]")
            return
        if chapter.notes_file:
            note_path = notes_path.parent.parent / chapter.notes_file
            if note_path.exists():
                from rich.markdown import Markdown
                console.print(Markdown(note_path.read_text(encoding="utf-8")))
            else:
                console.print("[yellow]笔记文件不存在[/yellow]")
        else:
            console.print("[yellow]该章节还没有笔记[/yellow]")
        return

    # 列出所有笔记
    if not notes_path.exists():
        console.print("[dim]还没有笔记[/dim]")
        return

    notes = sorted(notes_path.glob("*.md"))
    if not notes:
        console.print("[dim]还没有笔记[/dim]")
        return

    console.print("[bold]📝 笔记列表[/bold]")
    for n in notes:
        console.print(f"  📄 {n.stem}")


def cmd_help(args: list[str]) -> None:
    """帮助"""
    help_text = """
[bold cyan]EStudio — 有状态的结构化学习引擎[/bold cyan]

[bold]命令:[/bold]
  [yellow]new[/yellow] <主题名> [ID]    创建新学习主题
  [yellow]switch[/yellow] <主题ID>      切换到另一个主题
  [yellow]list[/yellow]                  列出所有主题
  [yellow]outline[/yellow]               为当前主题生成课程大纲 (AI)
  [yellow]status[/yellow]                查看当前进度和状态
  [yellow]learn[/yellow] [章节ID]        开始或继续学习
  [yellow]notes[/yellow] [章节ID]        查看笔记（不指定则列出所有笔记）
  [yellow]web[/yellow] [端口]            启动 Web UI（默认 http://127.0.0.1:7890）

[bold]学习中的命令:[/bold]
  输入 [yellow]'结束'[/yellow] 或 [yellow]'quit'[/yellow]    保存进度并结束本节
  输入 [yellow]'状态'[/yellow]            查看当前会话状态
  输入 [yellow]'复习'[/yellow]            快速做一道练习题

[bold]环境变量:[/bold]
  [dim]ESTUDIO_MODEL[/dim]     AI 模型 (默认: claude-sonnet-4-5-20250914)
  [dim]ESTUDIO_PROVIDER[/dim]  AI 提供商 (默认: anthropic)
  [dim]ANTHROPIC_API_KEY[/dim]  Anthropic API 密钥
  [dim]OPENAI_API_KEY[/dim]    OpenAI API 密钥
"""
    from rich.markdown import Markdown
    console.print(help_text)


# ═══════════════════════════════════════════════
# 命令路由
# ═══════════════════════════════════════════════

def cmd_web(args: list[str]) -> None:
    """启动 Web UI"""
    from .web import start_web
    port = int(args[0]) if args else 7890
    console.print(f"[bold cyan]EStudio Web UI 启动中...[/bold cyan]")
    console.print(f"[dim]打开浏览器访问 http://127.0.0.1:{port}[/dim]")
    start_web(port=port)


COMMANDS = {
    "new": cmd_new,
    "switch": cmd_switch,
    "list": cmd_list,
    "ls": cmd_list,
    "outline": cmd_outline,
    "status": cmd_status,
    "st": cmd_status,
    "learn": cmd_learn,
    "teach": cmd_learn,
    "notes": cmd_notes,
    "web": cmd_web,
    "help": cmd_help,
    "-h": cmd_help,
    "--help": cmd_help,
}


def main():
    """CLI 入口"""
    show_banner()

    args = sys.argv[1:]

    if not args:
        # 无参数：显示状态
        cmd_status([])
        console.print("\n[dim]输入 'estudio help' 查看所有命令[/dim]")
        return

    cmd_name = args[0].lower()
    cmd_args = args[1:]

    if cmd_name in COMMANDS:
        try:
            COMMANDS[cmd_name](cmd_args)
        except KeyboardInterrupt:
            console.print("\n[yellow]已取消[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ 错误: {e}[/red]")
            import traceback
            traceback.print_exc()
    else:
        console.print(f"[red]未知命令: {cmd_name}[/red]")
        console.print(f"可用命令: {', '.join(COMMANDS.keys())}")
        console.print("[dim]输入 'estudio help' 查看详细帮助[/dim]")


if __name__ == "__main__":
    main()
