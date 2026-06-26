# -*- coding: utf-8 -*-
"""
Web 端 AI 解释 —— SSE 流式代理。

设计要点：
- 前端永远不接触 api_key。所有 LLM 调用在本机后端完成，SSE 增量转发给浏览器。
- LLM 调用是纯网络 IO，不碰 mw.col，故直接在 aiohttp 后台线程池执行，
  不走 run_on_main_async（那是给 Qt 主线程操作用的）。
- thinking 降级 / ollama 鉴权判定 复用 api_client 单例的状态机与桌面端
  ai_explanation_dialog 的同款逻辑。
"""

import json
import traceback

import requests


def _is_ollama(api_url: str, model_name: str) -> bool:
    """ollama 本地模型：不设置 Authorization 头。"""
    return ("localhost" in api_url or "127.0.0.1" in api_url
            or "ollama" in (model_name or "").lower())


def build_messages(config, sentence: str, word: str, history: list) -> list:
    """构建对话 messages：system 留空 + 首条 user 为系统提示词 + 历史追问。"""
    from .ui.ai_explanation_dialog import build_prompt
    model_name = config.get("model_name", "")

    DEFAULT = {
        "vocab_level": "大学英语四级 CET-4 (4000词)",
        "learning_goal": "提升日常浏览英文网页与资料的流畅度",
        "difficulty_level": "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
        "sentence_length_desc": "中等长度句 (约25-40词): 通用对话及文章常用长度",
    }
    system_prompt = build_prompt(
        sentence=sentence,
        word_to_explain=word,
        vocab_level=config.get("vocab_level", DEFAULT["vocab_level"]),
        learning_goal=config.get("learning_goal", DEFAULT["learning_goal"]),
        difficulty_level=config.get("difficulty_level", DEFAULT["difficulty_level"]),
        sentence_length_desc=config.get("sentence_length_desc", DEFAULT["sentence_length_desc"]),
        # web 端不做例句保存，用精简提示词
        include_examples=False,
    )
    # qwen3 系列追加 /no_think，关闭思维链
    if "qwen3" in (model_name or "").lower():
        system_prompt += "\n/no_think"

    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": system_prompt},
    ]
    # 追加历史（history 内是首轮之后的 user/assistant 往返）
    for msg in (history or []):
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    return messages


def stream_chat(config, sentence: str, word: str, history: list):
    """
    生成器：流式调用 LLM，yield 出事件 dict。
    事件类型：
        {"type": "delta", "content": "..."}   增量文本
        {"type": "error", "message": "..."}   错误（非 200 / 网络异常 / thinking 不可用）
        {"type": "done"}                      流正常结束
    """
    from . import api_client

    api_url = config.get("api_url")
    api_key = config.get("api_key")
    model_name = config.get("model_name")

    if not api_url or not model_name:
        yield {"type": "error", "message": "请在配置中设置 API URL 和模型名称。"}
        return

    is_ollama = _is_ollama(api_url, model_name)
    if not is_ollama and not api_key:
        yield {"type": "error", "message": "请在配置中设置 API Key。"}
        return

    messages = build_messages(config, sentence, word, history)
    headers = ({"Content-Type": "application/json"} if is_ollama
               else {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    def make_payload():
        if api_client.support_thinking:
            return {"model": model_name, "messages": messages, "stream": True,
                    "thinking": {"type": "disabled"}}
        return {"model": model_name, "messages": messages, "stream": True}

    def do_request():
        return requests.post(api_url, headers=headers, json=make_payload(),
                             stream=True, timeout=60)

    try:
        response = do_request()
    except requests.exceptions.RequestException as e:
        yield {"type": "error", "message": f"网络错误: {e}"}
        return

    # thinking 不可用 → 降级重试一次
    if response.status_code != 200 and api_client.support_thinking:
        try:
            body = response.text
        except Exception:
            body = ""
        if "thinking" in body.lower():
            api_client.support_thinking = False
            try:
                response = do_request()
            except requests.exceptions.RequestException as e:
                yield {"type": "error", "message": f"网络错误: {e}"}
                return

    if response.status_code != 200:
        yield {"type": "error", "message": f"API 返回 {response.status_code}: {response.text[:300]}"}
        return

    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk:
                continue
            chunk_str = chunk.decode("utf-8", errors="ignore")
            for line in chunk_str.splitlines():
                if not line.startswith("data: "):
                    if "[DONE]" in line:
                        break
                    continue
                json_data = line[len("data: "):].strip()
                if json_data == "[DONE]":
                    yield {"type": "done"}
                    return
                try:
                    data = json.loads(json_data)
                except json.JSONDecodeError:
                    continue
                # 结尾帧/usage 帧 choices 可能为空，安全取值避免 IndexError
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}).get("content", "")
                if delta:
                    yield {"type": "delta", "content": delta}
    except requests.exceptions.RequestException as e:
        yield {"type": "error", "message": f"网络错误: {e}"}
        return
    except Exception as e:
        traceback.print_exc()
        yield {"type": "error", "message": f"意外错误: {e}"}
        return

    yield {"type": "done"}
