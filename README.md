# EStudio — 有状态的结构化学习引擎

> **对话是界面，课程树是骨架，掌握度是灵魂。**

EStudio 将 AI 对话式学习从"无限滚动的聊天窗口"升级为"有状态的结构化教学系统"。你的学习进度、掌握度、笔记、薄弱点——全被持久化保存，不会丢失。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置 AI API Key（二选一）
set ANTHROPIC_API_KEY=your-key    # 如果用 Claude
set OPENAI_API_KEY=your-key       # 如果用 OpenAI

# 3. 创建第一个学习主题
python -m src.main new "Python 全流程" python

# 4. 生成大纲
python -m src.main outline

# 5. 开始学习
python -m src.main learn

# 查看进度
python -m src.main status

# 或者使用 Web 学习中心（三栏界面：课程树 + 聊天 + 会话记录/复习）
python -m src.main web
```

---

## 核心概念

| 概念 | 说明 |
|---|---|
| **课程树** | 结构化的学习大纲，包含模块→章节→知识点，带进度状态 |
| **会话** | 一次学习对话，有明确边界（一章一节） |
| **掌握度** | 0~1 的数值，标记你对每个知识点的掌握程度 |
| **困惑锚点** | 你说"不懂"的时刻被自动记录，后续可回溯 |
| **复习队列** | 间隔重复系统，到期提醒你该复习什么 |

---

## 当前版本

**v0.1** — 核心骨架

- ✅ 多主题管理（创建/切换）
- ✅ AI 生成课程大纲
- ✅ 课程树可视化（rich 终端 UI）
- ✅ 对话学习 + 状态持久化
- ✅ 会话存档 + 自动 checkpoint
- ✅ 笔记自动生成
- ✅ 掌握度评估
- ✅ 复习提醒

详见 [docs/ROADMAP.md](docs/ROADMAP.md)

---

## 文档

- [DESIGN — 设计总纲](docs/DESIGN.md)（产品定位 / 架构 / 数据模型 / 会话设计 / 技术选型）
- [ROADMAP — 开发路线图](docs/ROADMAP.md)（唯一活文档，改代码前先改这里）

> 2026-08 文档熔铸：原 PRD / ARCHITECTURE / DATA_MODEL / SESSION_DESIGN / TECH_STACK 五篇合并为 DESIGN.md，原文备份在 `docs/legacy_docs_backup.zip`。

---

## 项目结构

```
EStudio/
├── src/
│   ├── main.py          # CLI 入口
│   ├── config.py        # 配置与路径
│   ├── data_models.py   # 数据模型（dataclass）
│   ├── store.py         # JSON 读写层
│   ├── curriculum.py    # 课程管理器
│   ├── knowledge.py     # 知识状态管理器
│   ├── session.py       # 会话管理器
│   ├── ai_provider.py   # AI 接口层
│   ├── ui.py            # rich CLI 界面
│   ├── web.py           # FastAPI Web UI（SSE 流式聊天 + 会话历史）
│   └── static/
│       └── index.html   # Web 前端（三栏玻璃拟态学习中心）
├── prompts/
│   └── teacher.md       # System Prompt 模板
├── data/                # 用户数据（gitignore）
├── docs/                # 设计文档
└── README.md
```

---

## 许可证

[MIT](LICENSE) © 2026 old884888