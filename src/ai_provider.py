"""AI 接口层 — 封装 LLM 调用，支持多模式，可切换厂商"""

import json
import os
import re
from typing import Optional

from .config import AI_MODEL, AI_PROVIDER, AI_MAX_TOKENS, PROMPTS_DIR


class AIProvider:
    """LLM 接口封装"""

    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
    ):
        self.model = model or AI_MODEL
        self.provider = provider or AI_PROVIDER

    def _load_prompt_template(self, name: str) -> str:
        """加载 Prompt 模板文件"""
        path = PROMPTS_DIR / f"{name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _resolve_model_id(self) -> str:
        """解析 litellm 格式的 model ID"""
        # 如果 model 已经带了 provider 前缀，直接返回
        if "/" in self.model:
            return self.model
        # 否则加上 provider 前缀
        return f"{self.provider}/{self.model}"

    def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        """发送对话请求，返回 AI 回复文本"""
        try:
            from litellm import completion

            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            model_id = self._resolve_model_id()
            response = completion(
                model=model_id,
                messages=full_messages,
                temperature=temperature,
                max_tokens=AI_MAX_TOKENS,
            )
            return response.choices[0].message.content

        except ImportError:
            return self._fallback_response(messages)
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
                env_var = f"{self.provider.upper()}_API_KEY"
                return (
                    "API 认证失败。请在项目根目录的 .env 文件中设置：\n"
                    f"  {env_var}=your-key\n\n"
                    f"当前提供商: {self.provider}\n"
                    f"当前模型: {self.model}\n"
                    f"错误: {error_msg}"
                )
            return f"AI 调用失败: {error_msg}"

    def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        include_reasoning: bool = False,
    ):
        """流式对话 —— 逐 token 返回

        include_reasoning=False（默认）时，yield 纯文本 chunk（CLI 用）。
        include_reasoning=True 时，yield 事件 dict：
            {"type": "thinking", "content": "..."}  模型思考过程（DeepSeek reasoner 等）
            {"type": "content", "content": "..."}   正式回复文本
        """
        try:
            from litellm import completion

            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            model_id = self._resolve_model_id()
            response = completion(
                model=model_id,
                messages=full_messages,
                temperature=temperature,
                max_tokens=AI_MAX_TOKENS,
                stream=True,
            )

            for chunk in response:
                if not chunk.choices or not chunk.choices[0].delta:
                    continue
                delta = chunk.choices[0].delta

                if include_reasoning:
                    # litellm 将各厂商的思考字段统一为 reasoning_content
                    reasoning = (
                        getattr(delta, "reasoning_content", None)
                        or getattr(delta, "reasoning", None)
                    )
                    if reasoning:
                        yield {"type": "thinking", "content": reasoning}
                    if delta.content:
                        yield {"type": "content", "content": delta.content}
                else:
                    if delta.content:
                        yield delta.content

        except ImportError:
            fallback = self._fallback_response(messages)
            yield (
                {"type": "content", "content": fallback}
                if include_reasoning else fallback
            )
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
                env_var = f"{self.provider.upper()}_API_KEY"
                error_text = f"\nAPI 认证失败。请在 .env 文件中设置 {env_var}\n错误: {error_msg}"
            else:
                error_text = f"\nAI 调用失败: {error_msg}"
            if include_reasoning:
                yield {"type": "content", "content": error_text}
            else:
                yield error_text

    def _fallback_response(self, messages: list[dict]) -> str:
        """Fallback: litellm 未安装时的演示模式"""
        last_msg = messages[-1]["content"] if messages else ""

        # 基本的响应逻辑
        if "大纲" in last_msg or "课程" in last_msg or "curriculum" in last_msg.lower():
            return self._demo_curriculum(last_msg)
        return (
            "📝 [演示模式] litellm 未安装，这是本地生成的响应。\n\n"
            "要启用真实 AI，请运行:\n"
            "  pip install litellm\n"
            "  并设置 API key 环境变量。\n\n"
            "你说了: " + last_msg[:200]
        )

    def _demo_curriculum(self, prompt: str) -> str:
        """演示模式：返回预设大纲 JSON"""
        # 尝试从 prompt 中提取主题
        subject = "编程"
        if "Python" in prompt or "python" in prompt:
            subject = "Python"
        elif "JavaScript" in prompt or "javascript" in prompt:
            subject = "JavaScript"

        outline = {
            "subject": f"{subject} 全流程",
            "modules": [
                {
                    "title": "基础语法",
                    "description": f"{subject} 的基本语法元素",
                    "chapters": [
                        "变量与数据类型",
                        "运算符与表达式",
                        "条件语句",
                        "循环",
                    ],
                },
                {
                    "title": "数据结构",
                    "description": "存储和操作数据的方式",
                    "chapters": [
                        "列表(List)/数组",
                        "字典(Dict)/对象",
                        "集合与元组",
                        "字符串操作",
                    ],
                },
                {
                    "title": "函数与模块化",
                    "description": "封装与复用代码",
                    "chapters": [
                        "函数定义与调用",
                        "参数与返回值",
                        "作用域与闭包",
                        "模块与包管理",
                    ],
                },
                {
                    "title": "面向对象编程",
                    "description": "以对象组织代码",
                    "chapters": [
                        "类与对象",
                        "继承与多态",
                        "封装与属性",
                        "特殊方法",
                    ],
                },
                {
                    "title": "实战项目",
                    "description": "综合运用所学知识",
                    "chapters": [
                        "命令行工具开发",
                        "文件处理与数据持久化",
                        "错误处理与调试",
                        "项目总结与回顾",
                    ],
                },
            ],
        }
        return json.dumps(outline, ensure_ascii=False, indent=2)


# 全局单例
_provider: Optional[AIProvider] = None


def get_ai() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = AIProvider()
    return _provider


def generate_curriculum(subject_name: str) -> dict:
    """让 AI 生成课程大纲"""
    ai = get_ai()

    system_prompt = ai._load_prompt_template("teacher")
    user_prompt = (
        f"请为「{subject_name}」生成一份从零到项目的学习大纲。\n\n"
        "要求：\n"
        "1. 分成 4-6 个模块\n"
        "2. 每个模块 3-5 个章节\n"
        "3. 按学习顺序排列\n"
        "4. 章节标题简洁（10字以内）\n\n"
        "请严格按以下 JSON 格式输出，不要输出其他内容：\n"
        '{"subject": "主题名", "modules": [{"title": "模块名", "description": "描述", "chapters": ["章节1", ...]}, ...]}'
    )

    response = ai.chat(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.5,
    )
    return _parse_curriculum_json(response)


def _parse_curriculum_json(text: str) -> dict:
    """从 AI 回复中提取 JSON"""
    # 尝试找 JSON 块
    json_match = re.search(r'\{[\s\S]*"modules"[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # 尝试整个文本
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 最后 fallback：返回演示大纲
    provider = get_ai()
    return json.loads(provider._demo_curriculum(text))


def generate_notes(
    subject_id: str,
    chapter_title: str,
    conversation: list[dict],
) -> str:
    """基于对话生成笔记"""
    ai = get_ai()

    conv_text = "\n".join(
        f"{'🧑 用户' if m['role']=='user' else '🤖 AI'}: {m['content']}"
        for m in conversation[-30:]  # 只取最近 30 条
    )

    system_prompt = (
        "你是 EStudio 的笔记助手。根据对话记录，生成一份结构化的学习笔记。\n\n"
        "格式要求（Markdown）：\n"
        "1. ## 核心概念 — 一句话概括\n"
        "2. ## 关键代码 — 提取对话中的代码片段，标注用途\n"
        "3. ## 你踩过的坑 — 用户出错或困惑的点\n"
        "4. ## 关联知识 — 和之前学的有什么联系\n"
        "5. ## 下次复习重点 — 哪些需要巩固\n"
        "保持简洁，只记录对话中出现过的内容，不要编造。"
    )

    response = ai.chat(
        messages=[{
            "role": "user",
            "content": f"主题: {chapter_title}\n\n对话记录:\n{conv_text}\n\n请生成笔记。",
        }],
        system_prompt=system_prompt,
        temperature=0.3,
    )
    return response
