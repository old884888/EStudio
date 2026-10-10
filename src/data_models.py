"""数据模型定义 — 所有核心数据结构"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


# ── 状态枚举 ───────────────────────────────────


class NodeStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"


class SubjectStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# ── 主题索引 ───────────────────────────────────


@dataclass
class SubjectProgress:
    total_chapters: int = 0
    completed: int = 0
    in_progress: int = 0
    current_node: Optional[str] = None


@dataclass
class SubjectEntry:
    id: str
    name: str
    status: SubjectStatus = SubjectStatus.NOT_STARTED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    progress: Optional[SubjectProgress] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SubjectEntry":
        d = dict(d)
        d["status"] = SubjectStatus(d["status"])
        if d.get("progress"):
            d["progress"] = SubjectProgress(**d["progress"])
        return cls(**d)


@dataclass
class SubjectsIndex:
    active_subject: Optional[str] = None
    subjects: list[SubjectEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "active_subject": self.active_subject,
            "subjects": [s.to_dict() for s in self.subjects],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SubjectsIndex":
        return cls(
            active_subject=d.get("active_subject"),
            subjects=[SubjectEntry.from_dict(s) for s in d.get("subjects", [])],
        )


# ── 课程节点 ───────────────────────────────────


@dataclass
class Chapter:
    id: str
    title: str
    status: NodeStatus = NodeStatus.NOT_STARTED
    mastery: Optional[float] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    session_count: int = 0
    last_position: Optional[str] = None  # 上次学到哪的自由文本
    struggles: list[str] = field(default_factory=list)
    notes_file: Optional[str] = None
    one_liner: Optional[str] = None  # 费曼一句话总结

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Chapter":
        d = dict(d)
        d["status"] = NodeStatus(d["status"])
        d.setdefault("struggles", [])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Module:
    id: str
    title: str
    description: str = ""
    status: NodeStatus = NodeStatus.NOT_STARTED
    order: int = 0
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["chapters"] = [c.to_dict() for c in self.chapters]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        d = dict(d)
        d["status"] = NodeStatus(d["status"])
        d["chapters"] = [Chapter.from_dict(c) for c in d.get("chapters", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ConceptDependency:
    depends_on: list[str] = field(default_factory=list)
    appears_in: list[str] = field(default_factory=list)


@dataclass
class Milestone:
    after_chapters: list[str] = field(default_factory=list)
    title: str = ""
    description: str = ""
    required_concepts: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.NOT_STARTED

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Milestone":
        d = dict(d)
        d["status"] = NodeStatus(d["status"])
        d.setdefault("after_chapters", [])
        d.setdefault("required_concepts", [])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Curriculum:
    version: str = "1.0"
    subject: str = ""
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: NodeStatus = NodeStatus.NOT_STARTED
    current_node: Optional[str] = None
    concept_graph: dict[str, ConceptDependency] = field(default_factory=dict)
    modules: list[Module] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        # Concept graph 需要特殊处理
        d["concept_graph"] = {
            k: asdict(v) for k, v in self.concept_graph.items()
        }
        d["modules"] = [m.to_dict() for m in self.modules]
        d["milestones"] = [m.to_dict() for m in self.milestones]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Curriculum":
        d = dict(d)
        d["status"] = NodeStatus(d["status"])
        d["modules"] = [Module.from_dict(m) for m in d.get("modules", [])]
        d["milestones"] = [Milestone.from_dict(m) for m in d.get("milestones", [])]
        cg = d.get("concept_graph", {})
        d["concept_graph"] = {
            k: ConceptDependency(**v) for k, v in cg.items()
        }
        d.setdefault("current_node", None)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    # ── 便利方法 ─────────────────────────────

    def get_node(self, node_id: str) -> Optional[Chapter]:
        """根据 ID 查找章节"""
        for mod in self.modules:
            for ch in mod.chapters:
                if ch.id == node_id:
                    return ch
        return None

    def get_module_of(self, node_id: str) -> Optional[Module]:
        """查找包含某个章节的模块"""
        for mod in self.modules:
            for ch in mod.chapters:
                if ch.id == node_id:
                    return mod
        return None

    def get_next_pending(self) -> Optional[Chapter]:
        """找到下一个未开始的章节"""
        for mod in sorted(self.modules, key=lambda m: m.order):
            for ch in mod.chapters:
                if ch.status in (NodeStatus.NOT_STARTED, NodeStatus.IN_PROGRESS):
                    return ch
        return None

    def progress_summary(self) -> dict:
        """返回进度概览"""
        total = sum(len(m.chapters) for m in self.modules)
        completed = sum(
            1 for m in self.modules for c in m.chapters
            if c.status == NodeStatus.COMPLETED
        )
        in_progress = sum(
            1 for m in self.modules for c in m.chapters
            if c.status == NodeStatus.IN_PROGRESS
        )
        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "not_started": total - completed - in_progress,
            "percent": round(completed / total * 100, 1) if total > 0 else 0,
        }

    def all_chapters(self) -> list[Chapter]:
        """扁平化所有章节"""
        result = []
        for mod in self.modules:
            result.extend(mod.chapters)
        return result


# ── 知识状态 ───────────────────────────────────


@dataclass
class MasteryEvidence:
    type: str  # "exercise_correct" | "could_explain" | "struggle_repeated"
    detail: str
    at: str


@dataclass
class MasteryRecord:
    mastery: float
    last_practiced: str
    evidence: list[MasteryEvidence] = field(default_factory=list)
    backtrack_suggestion: Optional[str] = None


@dataclass
class WeakPoint:
    concept: str
    detected_at: str
    severity: str  # "low" | "medium" | "high"
    occurrence_count: int
    suggested_action: str


@dataclass
class KnowledgeState:
    subject: str = ""
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    mastery_map: dict[str, MasteryRecord] = field(default_factory=dict)
    weak_points: list[WeakPoint] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "updated_at": self.updated_at,
            "mastery_map": {
                k: {
                    "mastery": v.mastery,
                    "last_practiced": v.last_practiced,
                    "evidence": [asdict(e) for e in v.evidence],
                    "backtrack_suggestion": v.backtrack_suggestion,
                }
                for k, v in self.mastery_map.items()
            },
            "weak_points": [asdict(w) for w in self.weak_points],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeState":
        mastery_map = {}
        for k, v in d.get("mastery_map", {}).items():
            evidence = [MasteryEvidence(**e) for e in v.get("evidence", [])]
            mastery_map[k] = MasteryRecord(
                mastery=v["mastery"],
                last_practiced=v["last_practiced"],
                evidence=evidence,
                backtrack_suggestion=v.get("backtrack_suggestion"),
            )
        weak_points = [WeakPoint(**w) for w in d.get("weak_points", [])]
        return cls(
            subject=d.get("subject", ""),
            updated_at=d.get("updated_at", ""),
            mastery_map=mastery_map,
            weak_points=weak_points,
        )


# ── 复习队列 ───────────────────────────────────


@dataclass
class ReviewEntry:
    chapter_id: str
    title: str
    completed_at: str
    mastery_at_completion: float
    review_count: int = 0
    next_review: Optional[str] = None
    review_interval_hours: int = 24
    notes_file: Optional[str] = None


# ── 困惑锚点 ───────────────────────────────────


@dataclass
class PainPoint:
    id: str
    concept: str
    triggered_at: str
    user_utterance: str
    resolved: bool = False
    resolved_at: Optional[str] = None
    resolution_note: Optional[str] = None
    occurrence_count: int = 1
