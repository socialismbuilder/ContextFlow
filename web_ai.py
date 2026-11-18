# -*- coding: utf-8 -*-
"""
Web 端 AI 解释 —— SSE 流式代理。

设计要点：
- 前端永远不接触 api_key。所有 LLM 调用在本机后端完成，SSE 增量转发给浏览器。
- LLM 调用是纯网络 IO，不碰 mw.col，故直接在 aiohttp 后台线程池执行，
  不走 run_on_main_async（那是给 Qt 主线程操作用的）。
- 提示词组装见 prompts.py，供应商差异（thinking 降级 / ollama 鉴权 / qwen3
  no_think）统一由 llm_client.chat_stream 处理。
"""

from . import llm_client
from . import prompts


def stream_chat(config, sentence: str, word: str, history: list):
    """
    生成器：流式调用 LLM，yield 出事件 dict。
    事件类型：
        {"type": "delta", "content": "..."}   增量文本
        {"type": "error", "message": "..."}   错误（非 200 / 网络异常 / thinking 不可用）
        {"type": "done"}                      流正常结束
    """
    messages = prompts.build_explanation_messages(config, sentence, word, history,
                                                  include_examples=True)
    yield from llm_client.chat_stream(config, messages)
