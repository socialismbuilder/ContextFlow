# -*- coding: utf-8 -*-
"""
LLM 统一客户端。

职责：把各家供应商的接口差异全部封装在本模块内部，对上层暴露标准接口：
- chat()          非流式对话（例句生成、连接测试）
- chat_stream()   流式对话（AI 解释对话框 / Web 端 SSE）
- fetch_available_models()   拉取模型列表
- test_connection()          连接测试

内部统一的供应商差异处理：
- 思考额度（thinking_mode）统一五档：off / low / medium / high / default，
  按供应商与模型自动翻译成对应参数（reasoning_effort / thinking.type /
  enable_thinking / thinking_budget），供应商不支持关思考或没有中间档位时
  就近归并；参数不被接受时自动降级重试（进程内记忆）
- qwen3 系列：off 档额外在最后一条 user 消息末尾追加 /no_think 作为兜底
- ollama 本地模型：不携带 Authorization 头

thinking_mode 取值（设置界面统一显示为 关/低/中/高/默认 五档）：
- "off"      关闭思考（供应商物理上关不掉时，后端自动降级为最低档）
- "low"/"medium"/"high"  思考额度档位
- "default"  跟随模型默认（不发送任何思考参数）
"""

import json
import traceback

import requests

# --- 思考参数降级状态（进程内共享）---
_thinking_params_supported = True

# 各档位的界面文案（设置界面使用；data 值写入 config.thinking_mode）
THINKING_MODE_LABELS = {
    "off": "关（不思考）",
    "low": "低",
    "medium": "中",
    "high": "高",
    "default": "默认（跟随模型）",
}

# 各档位对应的标准思考预算（token 数），供 thinking_budget 类接口使用
_THINKING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}


def is_thinking_params_supported() -> bool:
    """当前供应商是否还接受思考控制参数（失败降级后为 False）"""
    return _thinking_params_supported


def reset_thinking_state():
    """重置降级状态（如更换供应商/模型后调用）"""
    global _thinking_params_supported
    _thinking_params_supported = True


# ============================================================
# 内部工具：供应商判定与请求构造
# ============================================================

def _is_ollama(api_url: str, model_name: str) -> bool:
    """ollama 本地模型：不设置 Authorization 头。"""
    return ("localhost" in (api_url or "")
            or "127.0.0.1" in (api_url or "")
            or "ollama" in (model_name or "").lower())


def _is_qwen(model_name: str) -> bool:
    return "qwen" in (model_name or "").lower()


def _is_qwen3(model_name: str) -> bool:
    return "qwen3" in (model_name or "").lower()


def _thinking_mode(config: dict) -> str:
    """读取并归一化思考额度档位。兼容旧版取值：auto/disable→off，enable→default"""
    if isinstance(config, str):
        raw = config
    else:
        raw = (config or {}).get("thinking_mode", "off")
    if raw in ("auto", "disable"):
        raw = "off"
    elif raw == "enable":
        raw = "default"
    return raw if raw in THINKING_MODE_LABELS else "off"


def _thinking_payload(api_url: str, model_name: str, mode: str) -> dict:
    """按供应商/模型把统一档位翻译成该接口的思考控制参数。

    返回需要合并进请求体的 dict；"default"（跟随模型）返回空 dict。
    供应商关不掉思考或没有中间档位时，就近归并：
    - 关不掉（Grok/Gemini 3+/glm-5.3 等纯思考模型）：off → 最低档参数
    - 无 medium（DeepSeek effort 只有 low/high）：medium → high
    """
    if mode == "default":
        return {}
    if not _thinking_params_supported:
        return {}

    url = (api_url or "").lower()
    m = (model_name or "").lower()
    budget = _THINKING_BUDGETS.get(mode, 4096)

    # 1) Qwen / 阿里百练：enable_thinking + thinking_budget
    if _is_qwen(m) or "dashscope" in url:
        if mode == "off":
            return {"enable_thinking": False}
        return {"enable_thinking": True, "thinking_budget": budget}

    # 2) 火山方舟 / 豆包 Seed：thinking.type + thinking_budget
    if "volces.com" in url or "doubao" in m:
        if mode == "off":
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "thinking_budget": budget}

    # 3) OpenRouter：reasoning.effort（由其归一化到上游各家）
    if "openrouter" in url:
        effort = "none" if mode == "off" else mode
        return {"reasoning": {"effort": effort}}

    # 4) DeepSeek：开关 thinking.type + 力度 reasoning_effort（仅 low/high，medium 归并到 high）
    if "deepseek" in url:
        if mode == "off":
            return {"thinking": {"type": "disabled"}}
        effort = {"low": "low", "medium": "high", "high": "high"}.get(mode, "high")
        return {"reasoning_effort": effort, "thinking": {"type": "enabled"}}

    # 5) Kimi / Moonshot：thinking.type 开关（无档位，低中高等效）
    if "moonshot" in url or m.startswith("kimi") or "kimi" in m:
        return {"thinking": {"type": "disabled" if mode == "off" else "enabled"}}

    # 6) Grok（x.ai）：reasoning_effort（4.5+ 无法关闭思考，off 就近归并为最低档）
    if "grok" in m or "x.ai" in url:
        if mode == "off":
            return {"reasoning_effort": "low"}
        return {"reasoning_effort": mode}

    # 6b) Gemini（OpenAI 兼容层）：reasoning_effort → thinking_level
    #     （3 系起 Pro 类无法关闭，off 就近归并为 low）
    if "gemini" in m:
        effort = "low" if mode == "off" else mode
        return {"reasoning_effort": effort}

    # 7) GLM（智谱/硅基流动等托管）：thinking.type 开关
    #    （glm-5.3 等纯思考模型关不掉，报错会触发自动降级）
    if "glm" in m:
        return {"thinking": {"type": "disabled" if mode == "off" else "enabled"}}

    # 7) GPT 等 OpenAI 系：标准 reasoning_effort
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        effort = "none" if mode == "off" else mode
        return {"reasoning_effort": effort}

    # 8) 其他未知供应商兜底：off 用旧版 thinking 参数，档位用标准 reasoning_effort
    if mode == "off":
        return {"thinking": {"type": "disabled"}}
    return {"reasoning_effort": mode}


_THINKING_ERROR_KEYWORDS = ("thinking", "reasoning", "effort", "enable_thinking", "budget")


def _apply_no_think(messages: list, model_name: str, mode: str) -> list:
    """qwen3 系列在关思考时，在最后一条 user 消息末尾追加 /no_think 作为兜底。"""
    if mode != "off" or not _is_qwen3(model_name):
        return messages
    messages = [dict(m) for m in messages]
    for msg in reversed(messages):
        if msg.get("role") == "user":
            msg["content"] = (msg.get("content") or "") + "\n/no_think"
            break
    return messages


def _build_headers(api_url: str, api_key: str, model_name: str) -> dict:
    if _is_ollama(api_url, model_name):
        return {"Content-Type": "application/json"}
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _error_mentions_thinking(response) -> bool:
    """判断错误响应是否与思考控制参数相关（用于自动降级）。"""
    try:
        error_json = response.json()
        detail = str(error_json.get("error", {}).get("message", response.text))
    except Exception:
        try:
            detail = response.text
        except Exception:
            return False
    detail = detail.lower()
    return any(kw in detail for kw in _THINKING_ERROR_KEYWORDS)


def _disable_thinking_params_globally():
    global _thinking_params_supported
    _thinking_params_supported = False


# ============================================================
# 标准接口
# ============================================================

def chat(config, messages, *, stream=False, max_tokens=None, timeout=None):
    """非流式对话。返回 requests.Response；网络异常时返回 None。

    内部处理：qwen3 /no_think、关闭思考参数、失败自动降级重试一次。
    """
    api_url = (config or {}).get("api_url")
    api_key = (config or {}).get("api_key", "")
    model_name = (config or {}).get("model_name", "")
    mode = _thinking_mode(config)
    timeout = timeout or 30

    headers = _build_headers(api_url, api_key, model_name)
    messages = _apply_no_think(messages, model_name, mode)
    thinking_payload = _thinking_payload(api_url, model_name, mode)

    def make_payload():
        payload = {"model": model_name, "messages": messages, "stream": stream}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(thinking_payload)
        return payload

    try:
        response = requests.post(api_url, headers=headers, json=make_payload(), timeout=timeout)
    except requests.exceptions.RequestException as e:
        print(f"错误：[llm_client.chat] 网络错误：{e}")
        return None
    except Exception as e:
        print(f"错误：[llm_client.chat] 意外错误：{type(e).__name__} - {e}")
        return None

    # 思考参数不被接受 → 降级重试一次（去掉全部思考参数）
    if (response.status_code != 200 and thinking_payload
            and _error_mentions_thinking(response)):
        _disable_thinking_params_globally()
        print("INFO: [llm_client.chat] API 不接受思考控制参数，已降级并重试")
        thinking_payload = {}
        try:
            response = requests.post(api_url, headers=headers, json=make_payload(), timeout=timeout)
        except requests.exceptions.RequestException as e:
            print(f"错误：[llm_client.chat] 降级重试网络错误：{e}")
            return None

    return response


def chat_stream(config, messages, *, stop_event=None, timeout=None):
    """流式对话生成器。yield 事件 dict：
        {"type": "delta", "content": "..."}   增量文本
        {"type": "error", "message": "..."}   错误（非 200 / 网络异常）
        {"type": "done"}                      流正常结束

    stop_event: threading.Event，置位后尽快停止读取（用于用户关闭窗口）。
    """
    api_url = (config or {}).get("api_url")
    api_key = (config or {}).get("api_key", "")
    model_name = (config or {}).get("model_name", "")
    mode = _thinking_mode(config)
    timeout = timeout or 60

    if not api_url or not model_name:
        yield {"type": "error", "message": "请在配置中设置 API URL 和模型名称。"}
        return
    if not _is_ollama(api_url, model_name) and not api_key:
        yield {"type": "error", "message": "请在配置中设置 API Key。"}
        return

    headers = _build_headers(api_url, api_key, model_name)
    messages = _apply_no_think(messages, model_name, mode)
    thinking_payload = _thinking_payload(api_url, model_name, mode)

    def make_payload():
        payload = {"model": model_name, "messages": messages, "stream": True}
        payload.update(thinking_payload)
        return payload

    def do_request():
        return requests.post(api_url, headers=headers, json=make_payload(),
                             stream=True, timeout=timeout)

    try:
        response = do_request()
    except requests.exceptions.RequestException as e:
        yield {"type": "error", "message": f"网络错误: {e}"}
        return

    # 思考参数不被接受 → 降级重试一次（去掉全部思考参数）
    if response.status_code != 200 and thinking_payload and _error_mentions_thinking(response):
        _disable_thinking_params_globally()
        thinking_payload = {}
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
            if stop_event is not None and stop_event.is_set():
                break
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


def fetch_available_models(api_url: str, api_key: str) -> tuple:
    """获取模型列表。

    返回 (models, error)：
    - 成功：(模型 id 列表, None)
    - 失败：([], 面向用户的中文错误说明)
    """
    if not api_url or not api_key:
        return [], "请先填写 API URL 和 API Key"

    endpoint = api_url
    if "/chat/completions" in api_url:
        endpoint = api_url.split("/chat/completions")[0] + "/models"
    elif api_url.endswith("/completions"):
        endpoint = api_url.rsplit("/completions", 1)[0] + "/models"
    else:
        endpoint = api_url.rstrip("/") + "/models"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def fail(msg: str) -> tuple:
        print(f"错误：[fetch_available_models] {msg} ({endpoint})")
        return [], msg

    try:
        response = requests.get(endpoint, headers=headers, timeout=10)
    except requests.exceptions.Timeout:
        return fail("请求超时，请检查网络连接或 API 地址是否正确")
    except requests.exceptions.ConnectionError:
        return fail("网络连接失败，请检查网络连接或 API 地址是否正确")
    except Exception as e:
        return fail(f"请求失败：{e}")

    status = response.status_code
    if status in (401, 403):
        return fail(f"API Key 无效或已过期，请检查密钥是否正确（HTTP {status}）")
    if status == 404:
        return fail("该供应商不支持查询模型列表，请手动填写模型名称（HTTP 404）")
    if status == 429:
        return fail("请求过于频繁，请稍后再试（HTTP 429）")
    if status >= 500:
        return fail(f"供应商服务异常，请稍后再试（HTTP {status}）")
    if status != 200:
        return fail(f"获取模型列表失败，请检查 API 地址与密钥（HTTP {status}）")

    try:
        data = response.json()
    except Exception:
        return fail("接口返回的不是有效 JSON，可能不是标准的模型列表接口")

    raw = data.get("data", []) if isinstance(data, dict) else []
    models = [m.get("id") for m in raw if isinstance(m, dict) and m.get("id")]
    if not models:
        return fail("供应商未返回任何模型，可能不支持标准 /models 接口，请手动填写模型名称")
    return models, None


def test_connection(api_url: str, api_key: str, model_name: str,
                    timeout_seconds: int = 30, thinking_mode: str = "auto") -> tuple:
    """连接测试。返回 (结果文本, 错误说明或 None)。"""
    config = {
        "api_url": api_url,
        "api_key": api_key,
        "model_name": model_name,
        "thinking_mode": thinking_mode,
    }
    test_prompt = "不要有任何多余其他输出，重复一遍这个词: Hello"

    try:
        response = chat(config, [{"role": "user", "content": test_prompt}],
                        max_tokens=50, timeout=timeout_seconds)
    except requests.exceptions.Timeout:
        return None, f"请求在 {timeout_seconds} 秒后超时。"
    except requests.exceptions.RequestException as e:
        return None, f"HTTP请求错误: {str(e)}"
    except Exception as e:
        return None, f"发生意外错误: {str(e)}"

    if response is None:
        return None, "请求失败（网络错误），请检查网络与 API 地址。"

    if response.status_code != 200:
        error_msg_detail = "Unknown error"
        try:
            error_json = response.json()
            error_msg_detail = error_json.get("error", {}).get("message", response.text)
        except json.JSONDecodeError:
            error_msg_detail = response.text
        if _error_mentions_thinking(response) and not is_thinking_params_supported():
            error_msg_detail = "API不接受思考控制参数，已自动降级，请重新尝试。"
        return None, f"API错误 {response.status_code}: {str(error_msg_detail)[:200]}"

    try:
        response_json = response.json()

        if response_json.get("choices") and \
                isinstance(response_json["choices"], list) and \
                len(response_json["choices"]) > 0 and \
                response_json["choices"][0].get("message") and \
                isinstance(response_json["choices"][0]["message"], dict) and \
                response_json["choices"][0]["message"].get("content"):

            content = response_json["choices"][0]["message"]["content"]
            return content.strip(), None
        else:
            return response.text[:100] if response.text else "响应为空", "响应格式非预期，但连接已建立。"

    except json.JSONDecodeError:
        if response.text:
            return response.text[:50], None
        return None, "无法从API解码JSON响应。"
    except Exception as e:
        return None, f"发生意外错误: {str(e)}"
