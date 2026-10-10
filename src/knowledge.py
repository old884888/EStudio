"""知识状态管理器 — 掌握度 + 薄弱点 + 复习队列"""

from datetime import datetime, timedelta
from typing import Optional

from .config import knowledge_path, review_queue_path, pain_points_path
from .data_models import (
    KnowledgeState,
    MasteryEvidence,
    MasteryRecord,
    PainPoint,
    ReviewEntry,
    WeakPoint,
)
from .store import read_json, write_json


# ── 知识状态 ───────────────────────────────────


def load_knowledge(subject_id: str) -> KnowledgeState:
    path = knowledge_path(subject_id)
    data = read_json(path)
    if not data:
        return KnowledgeState(subject=subject_id)
    return KnowledgeState.from_dict(data)


def save_knowledge(ks: KnowledgeState) -> None:
    ks.updated_at = datetime.now().isoformat()
    write_json(knowledge_path(ks.subject), ks.to_dict())


def update_mastery(
    subject_id: str,
    concept: str,
    mastery: float,
    evidence_type: str,
    evidence_detail: str,
) -> None:
    """更新一个概念的掌握度"""
    ks = load_knowledge(subject_id)
    now = datetime.now().isoformat()

    if concept not in ks.mastery_map:
        ks.mastery_map[concept] = MasteryRecord(
            mastery=mastery,
            last_practiced=now,
        )

    record = ks.mastery_map[concept]
    record.mastery = max(0.1, min(1.0, mastery))
    record.last_practiced = now
    record.evidence.append(MasteryEvidence(
        type=evidence_type,
        detail=evidence_detail,
        at=now,
    ))

    # 如果 mastery < 0.5，添加到薄弱点
    if mastery < 0.5:
        existing = [w for w in ks.weak_points if w.concept == concept]
        if existing:
            existing[0].occurrence_count += 1
            existing[0].detected_at = now
        else:
            ks.weak_points.append(WeakPoint(
                concept=concept,
                detected_at=now,
                severity="medium" if mastery < 0.3 else "low",
                occurrence_count=1,
                suggested_action=f"回顾 {concept} 的基础概念和示例",
            ))
    else:
        # mastery >= 0.5 时移除薄弱点标记
        ks.weak_points = [w for w in ks.weak_points if w.concept != concept]

    save_knowledge(ks)


# ── 复习队列 ─────────────────────────────────


def load_review_queue(subject_id: str) -> list[ReviewEntry]:
    path = review_queue_path(subject_id)
    data = read_json(path)
    if not data:
        return []
    return [ReviewEntry(**item) for item in data]


def save_review_queue(subject_id: str, queue: list[ReviewEntry]) -> None:
    dq = [entry.__dict__ for entry in queue]
    write_json(review_queue_path(subject_id), dq)


def add_to_review_queue(
    subject_id: str,
    chapter_id: str,
    title: str,
    mastery: float,
    notes_file: Optional[str] = None,
) -> None:
    """学完一章后加入复习队列"""
    queue = load_review_queue(subject_id)
    now = datetime.now().isoformat()

    # 检查是否已存在
    for entry in queue:
        if entry.chapter_id == chapter_id:
            entry.review_count = 0  # 重置
            entry.next_review = (now + timedelta(hours=24)).isoformat()
            save_review_queue(subject_id, queue)
            return

    queue.append(ReviewEntry(
        chapter_id=chapter_id,
        title=title,
        completed_at=now.isoformat(),
        mastery_at_completion=mastery,
        next_review=(now + timedelta(hours=24)).isoformat(),
        notes_file=notes_file,
    ))
    save_review_queue(subject_id, queue)


def get_due_reviews(subject_id: str) -> list[ReviewEntry]:
    """获取到期需要复习的章节"""
    queue = load_review_queue(subject_id)
    now = datetime.now().isoformat()
    due = []
    for entry in queue:
        if entry.next_review:
            review_time = datetime.fromisoformat(entry.next_review)
            if now >= review_time:
                due.append(entry)
    return due


# ── 困惑锚点 ──────────────────────────────────


def load_pain_points(subject_id: str) -> list[PainPoint]:
    path = pain_points_path(subject_id)
    data = read_json(path)
    if not data:
        return []
    return [PainPoint(**item) for item in data]


def save_pain_points(subject_id: str, points: list[PainPoint]) -> None:
    write_json(pain_points_path(subject_id), [p.__dict__ for p in points])


def add_pain_point(
    subject_id: str,
    concept: str,
    user_utterance: str,
) -> PainPoint:
    """记录一个困惑时刻"""
    points = load_pain_points(subject_id)
    now = datetime.now().isoformat()

    # 检查是否已有同类困惑
    for pp in points:
        if pp.concept == concept and not pp.resolved:
            pp.occurrence_count += 1
            pp.triggered_at = now
            save_pain_points(subject_id, points)
            return pp

    pp = PainPoint(
        id=f"pp_{len(points)+1:03d}",
        concept=concept,
        triggered_at=now,
        user_utterance=user_utterance,
    )
    points.append(pp)
    save_pain_points(subject_id, points)
    return pp
