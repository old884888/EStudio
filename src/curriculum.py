"""课程管理器 — 课程树的 CRUD + 进度管理"""

from datetime import datetime
from typing import Optional

from .config import (
    curriculum_path,
    subjects_index_path,
)
from .data_models import (
    Chapter,
    Curriculum,
    Module,
    NodeStatus,
    SubjectEntry,
    SubjectProgress,
    SubjectStatus,
    SubjectsIndex,
)
from .store import read_json, write_json


# ── 主题索引 ───────────────────────────────────


def load_subjects() -> SubjectsIndex:
    """加载多主题索引"""
    data = read_json(subjects_index_path())
    if not data:
        return SubjectsIndex()
    return SubjectsIndex.from_dict(data)


def save_subjects(index: SubjectsIndex) -> None:
    write_json(subjects_index_path(), index.to_dict())


def get_active_subject() -> Optional[SubjectEntry]:
    """获取当前活跃的主题"""
    index = load_subjects()
    if not index.active_subject:
        return None
    for s in index.subjects:
        if s.id == index.active_subject:
            return s
    return None


def create_subject(subject_id: str, name: str) -> SubjectEntry:
    """创建一个新的学习主题"""
    index = load_subjects()

    # 检查是否已存在
    for s in index.subjects:
        if s.id == subject_id:
            raise ValueError(f"主题 '{subject_id}' 已存在")

    entry = SubjectEntry(id=subject_id, name=name)
    index.subjects.append(entry)
    index.active_subject = subject_id
    save_subjects(index)
    return entry


def switch_subject(subject_id: str) -> SubjectEntry:
    """切换到另一个主题"""
    index = load_subjects()
    for s in index.subjects:
        if s.id == subject_id:
            index.active_subject = subject_id
            save_subjects(index)
            return s
    raise ValueError(f"主题 '{subject_id}' 不存在。可用: {[s.id for s in index.subjects]}")


def update_subject_progress(subject_id: str, progress: SubjectProgress) -> None:
    """更新主题进度"""
    index = load_subjects()
    for s in index.subjects:
        if s.id == subject_id:
            s.progress = progress
            save_subjects(index)
            return


# ── 课程树 ────────────────────────────────────


def load_curriculum(subject_id: str) -> Optional[Curriculum]:
    """加载课程树"""
    path = curriculum_path(subject_id)
    data = read_json(path)
    if not data:
        return None
    return Curriculum.from_dict(data)


def save_curriculum(curriculum: Curriculum) -> None:
    """保存课程树"""
    curriculum.updated_at = datetime.now().isoformat()
    path = curriculum_path(curriculum.subject)
    write_json(path, curriculum.to_dict())


def init_curriculum(subject_id: str, subject_name: str, modules: list[dict]) -> Curriculum:
    """
    从 AI 生成的大纲初始化课程树。
    modules 格式: [{"title": "模块名", "chapters": ["章节1", "章节2", ...]}, ...]
    """
    mod_objs = []
    chapter_counter = 0
    for mi, m in enumerate(modules):
        chapters = []
        for ci, ch_title in enumerate(m.get("chapters", [])):
            chapter_counter += 1
            chapters.append(Chapter(
                id=f"m{mi+1}_c{ci+1}",
                title=ch_title,
            ))
        mod_objs.append(Module(
            id=f"m{mi+1}",
            title=m.get("title", f"模块 {mi+1}"),
            description=m.get("description", ""),
            order=mi + 1,
            chapters=chapters,
        ))

    curriculum = Curriculum(
        subject=subject_id,
        description=subject_name,
        modules=mod_objs,
    )

    save_curriculum(curriculum)

    # 更新主题索引进度
    update_subject_progress(
        subject_id,
        SubjectProgress(total_chapters=chapter_counter),
    )

    return curriculum


def get_chapter(curriculum: Curriculum, chapter_id: str) -> Optional[Chapter]:
    """查找章节"""
    return curriculum.get_node(chapter_id)


def mark_chapter_status(
    curriculum: Curriculum, chapter_id: str, status: NodeStatus
) -> None:
    """更新章节状态"""
    ch = curriculum.get_node(chapter_id)
    if ch is None:
        raise ValueError(f"章节 '{chapter_id}' 不存在")

    ch.status = status
    now = datetime.now().isoformat()

    if status == NodeStatus.IN_PROGRESS:
        ch.started_at = now
        curriculum.current_node = chapter_id
        curriculum.status = NodeStatus.IN_PROGRESS
    elif status == NodeStatus.COMPLETED:
        ch.completed_at = now
        ch.session_count += 1

    # 更新模块状态
    mod = curriculum.get_module_of(chapter_id)
    if mod:
        all_done = all(c.status == NodeStatus.COMPLETED for c in mod.chapters)
        any_started = any(c.status != NodeStatus.NOT_STARTED for c in mod.chapters)
        if all_done:
            mod.status = NodeStatus.COMPLETED
        elif any_started:
            mod.status = NodeStatus.IN_PROGRESS

    # 检查整体完成
    all_modules_done = all(m.status == NodeStatus.COMPLETED for m in curriculum.modules)
    if all_modules_done:
        curriculum.status = NodeStatus.COMPLETED

    # 更新当前节点
    if status == NodeStatus.COMPLETED:
        next_ch = curriculum.get_next_pending()
        curriculum.current_node = next_ch.id if next_ch else None

    save_curriculum(curriculum)

    # 更新主题索引
    prog = curriculum.progress_summary()
    update_subject_progress(
        curriculum.subject,
        SubjectProgress(
            total_chapters=prog["total"],
            completed=prog["completed"],
            in_progress=prog["in_progress"],
            current_node=curriculum.current_node,
        ),
    )
