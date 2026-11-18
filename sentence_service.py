# -*- coding: utf-8 -*-
"""
例句生成服务：编排「提示词组装 → LLM 调用 → 响应解析」全流程。

- 提示词组装见 prompts.py
- LLM 调用（供应商差异/thinking/流式）见 llm_client.py
"""

import json
import re
import traceback

from . import prompts
from . import llm_client


def generate(config, keyword, prompt=None):
    """同步调用AI接口生成包含关键词的例句，返回例句对列表；失败返回 []"""
    formatted_prompt = prompts.format_prompt(config, keyword, prompt)

    try:
        response = llm_client.chat(config, [{"role": "user", "content": formatted_prompt}])
        message_content = get_message_content(response, keyword)
        sentence_pairs = parse_response(message_content, keyword)
        if not sentence_pairs:
            return []
        return sentence_pairs
    except Exception as e:
        print(f"错误：[generate] 关键字 '{keyword}' 出现意外错误：{type(e).__name__} - {e}")
        traceback.print_exc()
        return []


def get_message_content(response, keyword):
    """从 OpenAI 兼容响应中提取 choices[0].message.content；失败返回空串"""
    if response is None:
        return ""
    if response.status_code != 200:
        try:
            error_json = response.json()
            error_msg_detail = error_json.get("error", {}).get("message", response.text)
            if llm_client._error_mentions_thinking(response) and not llm_client.is_thinking_params_supported():
                return f"API不接受思考控制参数，已自动降级，请重新尝试。错误详情：{error_msg_detail}"
        except Exception:
            pass
    try:
        response_json = response.json()
        return response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(
            f"错误：[get_message_content] 无法从API响应中提取/解析内容，关键词：'{keyword}'。"
            f"错误：{e}。响应文本：{response.text[:500]}")
        return ""


def parse_response(message_content, keyword):
    """将API返回的消息内容解析为句子对列表"""
    try:
        content_json = json.loads(message_content)
        raw_pairs = content_json.get("sentences")
    except json.JSONDecodeError:
        try:
            json_match = re.search(r'\{.*\}', message_content, re.DOTALL)
            if json_match:
                content_json = json.loads(json_match.group())
                raw_pairs = content_json.get("sentences")
            else:
                print(
                    f"错误：[parse_response] 关键字'{keyword}'的响应中未找到JSON内容：{message_content}")
                return []
        except json.JSONDecodeError:
            print(
                f"错误：[parse_response] 关键字'{keyword}'的响应非JSON格式：{message_content}")
            return []

    if not isinstance(raw_pairs, list):
        print(f"错误：[parse_response] 关键字'{keyword}'未找到有效sentences列表")
        return []

    valid_pairs = []
    for pair in raw_pairs:
        if isinstance(pair, list) and len(pair) == 2 and all(isinstance(item, str) for item in pair):
            valid_pairs.append(pair)
        else:
            print(f"警告：[parse_response] 关键字'{keyword}'跳过无效配对：{pair}")

    if not valid_pairs:
        print(f"警告：[parse_response] 关键字'{keyword}'未找到有效句子对")

    return valid_pairs


# --- 向后兼容别名（供历史调用方使用，新代码请直接使用上方函数）---
generate_ai_sentence = generate
parse_message_content_to_sentence_pairs = parse_response
