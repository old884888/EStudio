# EStudio — 设计总纲

> 由 PRD / ARCHITECTURE / DATA_MODEL / SESSION_DESIGN / TECH_STACK 五篇熔铸而成（2026-08-13）。
> 历史原文备份在 `docs/legacy_docs_backup.zip`。
> 开发路线见 [ROADMAP.md](ROADMAP.md) —— 那是唯一需要持续更新的活文档。

---

## 1. 产品定位

EStudio 是一款**有状态的学习 Agent**。它解决的核心问题：

> AI 辅助学习中，"对话窗口"是无限滚动的、会遗忘的，而学习过程是有结构、有进度、需要记忆的。

EStudio 把学习状态从对话上下文中**抽离**出来，持久化到结构化数据中，让对话只是教学界面，而非唯一的记忆体。

**核心原则：对话是瞬态的（ephemeral），数据是持久的（persistent）。**

### 目标用户与痛点

- 零基础到中级的学习者，用 AI 对话自学的人
- 痛点：怕学到一半忘记进度 / 怕对话太长 AI 丢失上下文 / 怕学了但没真掌握

### 核心用户故事

1. **启动与恢复**：打开工具，它告诉我上次学到哪、有未解决的困惑，问继续还是复习。
2. **结构化学习**：输入"学 Python"，AI 生成课程树，一节一节学，每节是一个有边界的会话。
3. **提问不丢进度**：中间跑偏多远都行，会话结束自动总结、更新进度、生成笔记。
4. **薄弱点追踪**："for 循环嵌套你卡了 2 次，可能是依赖的列表切片不扎实，要不要先回顾？"
5. **复习调度**：3 天前学的章节，系统提醒该复习了（间隔重复）。
6. **项目实战**：学完条件/循环/函数，系统弹出"你可以写一个命令行记账本了，要做吗？"

---

## 2. 功能全景

| 模块 | 优先级 | 说明 | 现状 |
|---|---|---|---|
| 课程树管理器 | P0 | 结构化大纲 + 进度状态 + CRUD | ✅ v0.1 |
| 会话管理器 | P0 | 会话边界 + 状态恢复 + 自动保存 | ✅ v0.1 |
| 笔记生成器 | P0 | 每节结束 AI 自动生成结构化笔记 | ✅ v0.1 |
| 掌握度追踪 | P1 | mastery 值 + 薄弱点检测 | ✅ v0.1 |
| 困惑锚点 | P1 | 困惑时刻标记 + 回溯诊断 | ✅ v0.1 |
| 复习调度 | P1 | 间隔重复提醒 | ✅ v0.1 |
| **CLI 命令控制** | P1 | 学习中心内执行终端命令 + 终端气泡 | 📋 雷一 |
| **IDE 模式** | P2 | 文件树 + 代码查看器 + 标记器 | 📋 雷二/雷三 |
| 概念依赖图 | P1 | 概念前置关系，辅助诊断 | 待做 |
| 项目里程碑 | P2 | 课程树中嵌入实战项目节点 | 待做 |
| 学习模式切换 | P2 | 学习/练习/复习/项目/查阅 | 待做 |
| 自适应节奏 | P2 | 根据 mastery 趋势调整教学速度 | 待做 |
| 知识图谱导出 | P3 | 可视化已学知识 | 待做 |

### 非功能需求

| 需求 | 说明 |
|---|---|
| 本地优先 | 所有数据在本地文件系统，不依赖云服务 |
| 对话上下文精简 | 每个会话应尽量短，防止上下文溢出 |
| AI 无关 | 不绑定特定 AI 服务商（litellm 抽象） |
| 可中断可恢复 | 任意时刻关闭，下次打开恢复状态 |
| 离线优先（Web UI） | 前端零外部依赖，断网可用 |

---

## 3. 系统架构

```
┌──────────────────────────────────────────────────┐
│              CLI (rich)  /  Web UI (三栏)          │
│     课程树 │ 聊天 │ 学习面板（会话记录/复习）        │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│                Session Manager                    │
│    加载状态 → 教学 → 流式输出 → 定期存档 → 归档     │
└────────┬───────────────────┬─────────────────────┘
         │                   │
┌────────▼────────┐  ┌───────▼────────┐
│   State Store    │  │  AI Provider   │
│  (JSON 文件系统)  │  │  (litellm)     │
└────────┬────────┘  └────────────────┘
         │
┌────────▼─────────────────────────────────────────┐
│                  Data Layer                       │
│ curriculum.json │ knowledge.json │ review_queue   │
│ pain_points.json│ subjects.json  │ notes/*.md     │
│ sessions/*.json │（未来：projects.json, markers） │
└──────────────────────────────────────────────────┘
```

### 模块职责（对应真实代码）

| 模块 | 文件 | 职责 |
|---|---|---|
| 课程管理器 | `src/curriculum.py` | 课程树 CRUD、进度、节点状态机 |
| 会话管理器 | `src/session.py` | 会话生命周期、checkpoint、归档（总结/掌握度/笔记/复习入队） |
| 知识状态管理器 | `src/knowledge.py` | mastery、薄弱点、复习队列、困惑锚点 |
| AI 接口层 | `src/ai_provider.py` | LLM 封装（多厂商）、流式输出、思考流（reasoning） |
| 存储层 | `src/store.py` | JSON 原子读写 |
| 数据模型 | `src/data_models.py` | dataclass 定义 |
| CLI | `src/main.py` + `src/ui.py` | 命令路由 + rich 界面 |
| Web UI | `src/web.py` + `src/static/index.html` | FastAPI + SSE 流式、三栏前端 |

### AI Provider 的四种模式（System Prompt 差异）

- **教学模式**（teacher）：讲解者——讲概念 + 给例子 + 引导思考
- **练习模式**（exercise）：出题者——出题 + 判题 + 点评，不给直接答案
- **复习模式**（review）：测试者——快速提问 + 检测遗忘
- **项目模式**（mentor）：导师——引导方向，不替写代码

### 数据流（一次完整学习）

```
启动 → Session 加载 curriculum/knowledge/review_queue → 展示上次位置+待复习
  → 构造 System Prompt（注入 current_node + 薄弱点 + 困惑锚点）
  → 对话循环（用户输入 → AI 流式回复 → 30s 自动 checkpoint）
  → "结束本节" → AI 总结（summary/mastery/struggles）
  → 更新课程树节点 → 更新 knowledge → mastery≥0.6 入复习队列
  → 生成笔记 notes/{chapter_id}_{title}.md → 会话封档 sessions/
```

---

## 4. 数据模型

所有数据存为 JSON，便于 AI 直接读写。不使用数据库——保持简单。
统一约定：带 `version` 字段便于演进；`updated_at` 用于冲突检测；写入用原子写（temp → rename）。

### 4.1 课程树 `curriculum.json`

```jsonc
{
  "version": "1.0",
  "subject": "Python 全流程",
  "description": "从零基础到能独立开发命令行工具",
  "status": "in_progress",            // not_started | in_progress | completed | paused
  "current_node": "m1_c2",            // 当前正在学的节点 ID
  "concept_graph": {                  // 概念依赖图（未来）
    "list_comprehension": { "depends_on": ["lists", "for_loops"], "appears_in": ["m2_c2"] }
  },
  "modules": [
    {
      "id": "m1", "title": "基础语法", "order": 1, "status": "in_progress",
      "chapters": [
        {
          "id": "m1_c1", "title": "变量与数据类型",
          "status": "completed",       // not_started | in_progress | completed | paused
          "mastery": 0.85, "session_count": 1,
          "last_position": "讲完 if/elif 执行顺序，还没讲嵌套条件",
          "struggles": ["elif 的执行顺序"],
          "notes_file": "notes/m1_c1_变量与数据类型.md",
          "one_liner": "数据有类型，变量是名字，Python 是动态类型的"
        }
      ]
    }
  ],
  "milestones": [                     // 项目里程碑（未来）
    { "after_chapters": ["m1_c3"], "title": "猜数字游戏", "required_concepts": ["variables", "conditionals", "loops"] }
  ]
}
```

**节点状态机**：`not_started → in_progress → completed`；完成后 mastery ≥ 0.6 → 入复习队列，否则标记待重学。

### 4.2 知识状态 `knowledge.json`

```jsonc
{
  "subject": "Python 全流程",
  "updated_at": "2026-07-17T14:30:00",
  "mastery_map": {
    "variables": {
      "mastery": 0.85, "last_practiced": "2026-07-17T11:30:00",
      "evidence": [
        { "type": "exercise_correct", "detail": "变量赋值练习全对", "at": "..." },
        { "type": "could_explain", "detail": "能用自己的话解释动态类型", "at": "..." }
      ]
    }
  },
  "weak_points": [
    {
      "concept": "conditionals_if_elif", "detected_at": "...",
      "severity": "medium",               // low | medium | high
      "occurrence_count": 3,
      "suggested_action": "用流程图可视化 if/elif/else 的执行流程"
    }
  ]
}
```

**mastery 标尺**：0.9+ 能讲清楚 / 0.7-0.9 练习少错 / 0.4-0.6 需提示 / 0.1-0.3 基本不会。
**衰减**：超过复习间隔未复习 → mastery × 0.8；同一困惑重复触发 → 标记"需要回溯"。

### 4.3 困惑锚点 `pain_points.json`

```jsonc
[
  {
    "id": "pp_001", "concept": "elif 执行顺序",
    "triggered_at": "2026-07-17T14:32:00",
    "user_utterance": "那如果前面有个 if 已经满足了，elif 还会执行吗？",
    "resolved": false, "resolved_at": null, "occurrence_count": 2
  }
]
```

**困惑锚点 vs 薄弱点**：

| | 困惑锚点 (Pain Point) | 薄弱点 (Weak Point) |
|---|---|---|
| 本质 | 事件 | 状态 |
| 来源 | 用户的困惑时刻（说"不懂"/反复问） | mastery 计算得出 |
| 时效 | 解决后标记 resolved | 持续存在直到重新评估 |

### 4.4 复习队列 `review_queue.json`

```jsonc
[
  {
    "chapter_id": "m1_c1", "title": "变量与数据类型",
    "completed_at": "...", "mastery_at_completion": 0.85,
    "review_count": 0, "next_review": "2026-07-18T12:00:00",
    "review_interval_hours": 24, "notes_file": "notes/m1_c1_变量与数据类型.md"
  }
]
```

**间隔算法**：初始 24h；复习后按表现调整——轻松 ×2.5 / 一般 ×1.5 / 吃力 ×1.0（重置）/ 忘记 ×0.5 + 建议重学。

### 4.5 会话存档 `sessions/sess_{chapter_id}_{timestamp}.json`

```jsonc
{
  "session_id": "sess_m1_c1_20260717T143605",
  "subject_id": "python", "chapter_id": "m1_c1",
  "started_at": "...", "ended_at": null,
  "status": "active",                 // active | completed
  "message_count": 45,
  "conversation": [                   // 封档时写入完整对话；checkpoint 阶段只有元数据
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

### 4.6 笔记 `notes/{chapter_id}_{title}.md`

五段式模板：**核心概念**（一句话）→ **关键代码**（标注用途）→ **你踩过的坑** → **与前面知识的关联** → **下次复习重点**。只记录对话中出现过的内容，不编造。

### 4.7 多主题索引 `subjects.json`

```jsonc
{
  "active_subject": "python",
  "subjects": [
    { "id": "python", "name": "Python 全流程", "status": "in_progress",
      "progress": { "total_chapters": 20, "completed": 3 } }
  ]
}
```

---

## 5. 会话设计

### 5.1 会话的哲学

> 一次会话 = 一个章节。对话可以长，但不能无边界。

| | 传统 AI Chat | EStudio 会话 |
|---|---|---|
| 边界 | 无限滚动 | 一章一节 |
| 上下文 | 越来越长，被截断 | 会话内完整，会话间靠状态桥接 |
| 状态 | 消失 | 持久化到 JSON |
| 结束时 | 用户自己记结论 | 自动总结 + 生成笔记 |
| 中断 | 重新来 | 自动 checkpoint，可恢复 |

### 5.2 生命周期

```
START → 加载课程树 + 知识状态，展示上次位置 + 待复习
  → WARMUP：问候语注入（上次学到哪 / 待复习 / 未解决困惑 / 上次卡点）
  → TEACH：对话循环（AI 讲解 ↔ 用户提问 ↔ 小练习；每 30s 自动 checkpoint）
  → 用户说"结束"或内容自然结束
  → WRAP UP：AI 总结（一句话 summary / mastery 判定 / struggles 提取）
    → 更新课程树 → 更新 knowledge → 入复习队列 → 生成笔记 → 会话封档
  → IDLE
```

**中断恢复**：检测到 `status = "active"` 且无 `ended_at` → 提示"检测到你在 X 中断了学习，当时正在学 Y，要继续吗？[继续] [从头开始] [先复习]"

### 5.3 System Prompt 要点

**TEACH（教学主循环）**：
1. 每次只讲一个概念点，讲完给最小代码示例
2. 示例后问用户是否理解；理解确认后再往下
3. 跑偏问题：回答后礼貌拉回本章主题
4. 连续 3 次问同一概念 → 标记困惑锚点，换一种方式讲
5. **不直接给完整代码答案** → 给思路或伪代码，让用户先写
6. 用户答对练习 → 自然过渡到下一概念；章节讲完 → 提示可以结束

**WRAP UP（归档总结）**：输出 JSON —— `summary`（一句话）/ `mastery`（0-1，附理由）/ `struggles`（带证据）。

**练习模式**：3 道递增难度题 → 提交后判对错，错则给关键提示（不给答案），3 次修改机会 → 全对 0.8+ / 对2题 0.6-0.7 / 对1题 0.3-0.5 标薄弱 / 全错 0.1-0.3 建议回溯依赖概念。

**复习模式**：费曼检验（用自己的话概括）→ 3 个核心问题 → 调整 review_interval（全对 ×2.5 / 需提示 ×1.5 / 基本忘了 → mastery 0.3 建议重学）。

### 5.4 AI 行为约束（所有模式通用）

1. **不替用户写代码**：给提示、伪代码、思路，等用户写了再点评
2. **不跳过理解检验**：每个概念讲完必须确认理解
3. **不无限发散**：跑偏后礼貌拉回
4. **不糊弄**：不确定的直说，不编造
5. **记录就是力量**：检测到困惑信号 → 写入 pain_point

---

## 6. 技术选型（结论）

| 选型 | 答案 | 理由 |
|---|---|---|
| 语言 | Python ≥3.11 | 学习工具 + 学习过程一举两得；AI 对 Python 代码质量最高 |
| CLI | rich + prompt_toolkit | 美化输出 + 交互输入 |
| 数据 | JSON + Markdown | 结构化状态 AI 可直接读写；无数据库，保持简单 |
| AI | litellm | 不锁定厂商，可切换 DeepSeek/Anthropic/OpenAI |
| Web | FastAPI + SSE + 原生三栏前端 | 流式聊天；前端零外部依赖，离线可用 |
| 多主题 | v0.1 起支持 | 只是一个 subjects.json + 目录结构 |

（详细选型论证见备份包内 TECH_STACK.md，已火化，无需再看。）
