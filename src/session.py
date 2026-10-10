"""会话管理器 — 学习会话的完整生命周期"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .ai_provider import get_ai, generate_notes
from .config import notes_dir, sessions_dir
from .curriculum import (
    load_curriculum,
    mark_chapter_status,
    save_curriculum,
)
from .data_models import (
    Chapter,
    Curriculum,
    KnowledgeState,
    NodeStatus,
    PainPoint,
    ReviewEntry,
    SubjectEntry,
)
from .knowledge import (
    add_pain_point,
    add_to_review_queue,
    get_due_reviews,
    load_knowledge,
    load_pain_points,
    save_knowledge,
    update_mastery,
)
from .store import read_json, write_json
from .executor import CMD_FENCE


class Session:
    """一次学习会话"""

    def __init__(self, subject_entry: SubjectEntry, chapter: Chapter):
        self.subject = subject_entry
        self.chapter = chapter
        self.conversation: list[dict] = []  # [{"role": "user|assistant", "content": "..."}]
        self.ai = get_ai()
        self.curriculum: Optional[Curriculum] = None
        self.knowledge: Optional[KnowledgeState] = None
        self.due_reviews: list[ReviewEntry] = []
        self.pain_points: list[PainPoint] = []
        self.tool_log: list[dict] = []  # 会话内执行过的命令记录（雷一）

        # 会话存档路径
        self.session_id = f"sess_{chapter.id}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        self.session_path = sessions_dir(subject_entry.id) / f"{self.session_id}.json"

    def start(self) -> str:
        """启动会话，返回问候语"""
        self.curriculum = load_curriculum(self.subject.id)
        self.knowledge = load_knowledge(self.subject.id)
        self.due_reviews = get_due_reviews(self.subject.id)
        self.pain_points = load_pain_points(self.subject.id)

        # 标记章节为学习中
        if self.chapter.status == NodeStatus.NOT_STARTED:
            mark_chapter_status(self.curriculum, self.chapter.id, NodeStatus.IN_PROGRESS)
        self.chapter.status = NodeStatus.IN_PROGRESS

        # 构建系统 prompt
        system_prompt = self.build_system_prompt()

        # 构建启动消息
        greeting = self._build_greeting()

        self.conversation.append({"role": "assistant", "content": greeting})
        self.save_checkpoint()

        return greeting

    def build_system_prompt(self, enable_tools: bool = False) -> str:
        """构建教学模式的 System Prompt"""
        prompt = (
            "你是 EStudio 的教学老师，正在教一位学习者。\n\n"
            "## 教学规则\n"
            "1. 每次只讲一个概念点，讲完给最小代码示例\n"
            "2. 示例后问用户是否理解\n"
            "3. 用户连续 3 次问同一概念 → 换一种方式讲，标记为困惑点\n"
            "4. 不要直接给完整代码答案 → 给思路或伪代码，让用户先尝试\n"
            "5. 用户问题跑偏时，回答后拉回当前主题\n\n"
        )

        if self.curriculum:
            prompt += (
                f"## 当前上下文学\n"
                f"- 课程: {self.curriculum.description}\n"
                f"- 当前模块: {self.curriculum.get_module_of(self.chapter.id).title if self.curriculum.get_module_of(self.chapter.id) else '未知'}\n"
                f"- 当前章节: {self.chapter.title}\n"
            )
            if self.chapter.last_position:
                prompt += f"- 上次进度: {self.chapter.last_position}\n"

        # 注入薄弱点
        if self.knowledge and self.knowledge.weak_points:
            weak = ", ".join(w.concept for w in self.knowledge.weak_points[:3])
            prompt += f"\n⚠️ 用户薄弱点: {weak}\n"

        # 注入困惑锚点
        unresolved = [pp for pp in self.pain_points if not pp.resolved]
        if unresolved:
            pp_concepts = ", ".join(pp.concept for pp in unresolved[:3])
            prompt += f"❓ 未解决的困惑: {pp_concepts}\n"

        # 命令执行协议（仅 Web 工具流开启）
        if enable_tools:
            prompt += (
                f"\n## 命令执行协议（重要）\n"
                f"当你需要真实运行终端命令时（查看文件、运行代码、跑测试等），"
                f"你的整条回复必须【只】包含以下格式的代码块，不要有任何其他文字：\n\n"
                f"```{CMD_FENCE}\n"
                f'{{"cmd": "要执行的命令", "cwd": "可选：相对项目根目录的工作目录", "reason": "一句话说明为什么执行"}}\n'
                f"```\n\n"
                f"系统会执行命令并把真实结果回传给你，然后你基于结果继续教学。\n"
                f"规则：\n"
                f"1. 只有确实需要真实执行时才使用；能直接回答就不要用\n"
                f"2. 命令会被安全检查：危险命令需要用户批准，被拦截的命令不要再尝试\n"
                f"3. 收到执行结果后正常用文字继续，除非还需要执行命令\n"
                f"4. 绝不要虚构执行结果\n"
            )

        return prompt

    def _build_greeting(self) -> str:
        """构建启动问候语"""
        parts = [f"📚 开始学习：**{self.chapter.title}**"]

        if self.chapter.last_position:
            parts.append(f"\n💡 上次进度: {self.chapter.last_position}")

        if self.chapter.struggles:
            struggles = "、".join(self.chapter.struggles)
            parts.append(f"\n⚠️ 之前卡住的地方: {struggles}")

        if self.due_reviews:
            reviews = "、".join(r.title for r in self.due_reviews[:2])
            parts.append(f"\n📝 待复习: {reviews}")

        if self.pain_points:
            unresolved = [pp for pp in self.pain_points if not pp.resolved]
            if unresolved:
                parts.append(f"\n❓ 未解决的困惑: {unresolved[0].concept}")

        parts.append("\n\n准备好了吗？我们开始吧！有什么问题随时问 😊")
        return "\n".join(parts)

    # ── 公共原语（CLI 与 Web 工具流共用） ──────────

    def append_user_message(self, user_input: str) -> None:
        """记录用户消息（含困惑信号检测）"""
        confusion_keywords = ["不懂", "不明白", "没懂", "不会", "还是没明白", "what", "huh"]
        if any(kw in user_input.lower() for kw in confusion_keywords):
            add_pain_point(
                self.subject.id,
                self.chapter.title,
                user_input,
            )
        self.conversation.append({"role": "user", "content": user_input})

    def append_assistant_message(self, text: str) -> None:
        """记录 AI 回复并存档检查点"""
        self.conversation.append({"role": "assistant", "content": text})
        self.save_checkpoint()

    def chat(self, user_input: str) -> str:
        """处理用户输入，返回 AI 回复"""
        self.append_user_message(user_input)

        response = self.ai.chat(
            messages=self.conversation,
            system_prompt=self.build_system_prompt(),
        )

        self.append_assistant_message(response)
        return response

    def chat_stream(self, user_input: str):
        """流式处理用户输入，逐 token 返回"""
        self.append_user_message(user_input)

        # 收集完整回复
        full_response = ""

        for chunk in self.ai.chat_stream(
            messages=self.conversation,
            system_prompt=self.build_system_prompt(),
        ):
            full_response += chunk
            yield chunk

        self.append_assistant_message(full_response)

    def end(self) -> str:
        """结束会话，追归档"""
        if self.curriculum is None:
            self.curriculum = load_curriculum(self.subject.id)

        # 用 AI 分析会话，估计掌握度
        summary = self._ai_summarize()

        # 更新课程状态
        self.chapter.last_position = summary.get("summary", "")

        # 从 AI 回复中提取掌握度
        mastery_str = summary.get("mastery", "0.5")
        try:
            mastery = float(mastery_str)
        except (ValueError, TypeError):
            mastery = 0.5

        self.chapter.mastery = mastery
        self.chapter.session_count += 1

        # 提取薄弱点
        struggles = summary.get("struggles", [])
        if isinstance(struggles, str):
            struggles = [struggles]
        self.chapter.struggles = struggles

        # 根据掌握度决定状态
        if mastery >= 0.6:
            mark_chapter_status(self.curriculum, self.chapter.id, NodeStatus.COMPLETED)
            # 加入复习队列
            add_to_review_queue(
                self.subject.id,
                self.chapter.id,
                self.chapter.title,
                mastery,
            )
        else:
            # 掌握度不够，保持 in_progress
            mark_chapter_status(self.curriculum, self.chapter.id, NodeStatus.IN_PROGRESS)

        # 更新知识状态
        if mastery >= 0.6:
            update_mastery(
                self.subject.id,
                self.chapter.id,
                mastery,
                "exercise_correct" if mastery > 0.8 else "could_explain",
                f"会话 {self.session_id} 完成",
            )
        else:
            update_mastery(
                self.subject.id,
                self.chapter.id,
                mastery,
                "struggle_repeated",
                f"掌握度不足: {mastery}",
            )

        # 生成笔记
        notes_md = generate_notes(
            self.subject.id,
            self.chapter.title,
            self.conversation,
        )
        note_path = notes_dir(self.subject.id) / f"{self.chapter.id}_{self.chapter.title}.md"
        note_path.write_text(notes_md, encoding="utf-8")
        self.chapter.notes_file = str(note_path.relative_to(notes_dir(self.subject.id).parent.parent))

        save_curriculum(self.curriculum)

        # 保存会话存档
        self._save_final()

        return (
            f"✅ 本节结束！\n\n"
            f"📊 掌握度评估: {mastery:.0%}\n"
            f"{'✅ 已完成本节' if mastery >= 0.6 else '⚠️ 建议巩固后再继续'}\n"
            f"📝 笔记已保存: {note_path.name}\n"
        )

    def _ai_summarize(self) -> dict:
        """让 AI 总结本次会话"""
        conv_text = "\n".join(
            f"{m['role']}: {m['content'][:500]}" for m in self.conversation[-20:]
        )

        prompt = (
            "请基于以下学习对话，输出一个 JSON 对象（不要输出其他内容）：\n"
            "{\n"
            '  "summary": "一句话总结本节内容",\n'
            '  "mastery": 0.0-1.0 之间的数字，评估用户的掌握程度,\n'
            '  "struggles": ["用户有困难的点1", "点2"]\n'
            "}\n\n"
            f"对话记录:\n{conv_text}"
        )

        response = self.ai.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        # 解析 JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {"summary": "本节内容", "mastery": 0.5, "struggles": []}

    def save_checkpoint(self) -> None:
        """保存检查点"""
        data = {
            "session_id": self.session_id,
            "subject_id": self.subject.id,
            "chapter_id": self.chapter.id,
            "started_at": datetime.now().isoformat(),
            "status": "active",
            "message_count": len(self.conversation),
            "last_position": self.chapter.last_position,
        }
        write_json(self.session_path, data)

    def _save_final(self) -> None:
        """封档保存"""
        data = {
            "session_id": self.session_id,
            "subject_id": self.subject.id,
            "chapter_id": self.chapter.id,
            "started_at": datetime.now().isoformat(),
            "ended_at": datetime.now().isoformat(),
            "status": "completed",
            "message_count": len(self.conversation),
            "conversation": self.conversation,
            "tool_log": self.tool_log,
        }
        write_json(self.session_path, data)
