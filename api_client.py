import requests
import json
import aqt
import concurrent.futures
import traceback
import typing # Add typing for Optional
import re
# Configuration details are dynamically loaded from user settings via config_manager

# 默认提示词模板 - 现在从配置中读取
DEFAULT_PROMPT_TEMPLATE = '''
请为{language}学习者生成5个包含关键词 ‘{world}’ 的{language}例句，并附带中文翻译。

学习者信息：
- 当前词汇量大致为：{vocab_level}
- 学习目标是：{learning_goal}
- 句子最大难度：{difficulty_level}
- 句子最大长度:{sentence_length_desc}

例句生成规则：
- 难度控制原则：评估关键词 '{world}' 的固有难度，与设定的目标句子难度，生成的句子整体难度必须同时低于关键词的固有难度和设定的目标难度。
- 提供的关键词 '{world}' 是一个完整的词汇。它可以是原形、复数、过去式等屈折形式，或作为组合词的一部分，但不能是该词根衍生的其他词汇。
（例如，如果关键词是 "book"，例句中可以使用 "books" 或 "notebook" 中的 "book" 部分，前提是notebook的book代表着原本含义）
- 绝对禁止将关键词用作前后缀来构成一个不同的词汇，或使用与关键词同根但意义完全不同的衍生词。
（例如，给出关键词book,例句不能使用booking;给出king，例句不能使用kingdom）
- 语境应尽量与学习目标 ({learning_goal}) 相关，或者为通用场景。
- 每个例句必须包含关键词 ‘{world}’。
- 5个例句应尽量全面的覆盖关键词的各种用法和含义。

例如：如果关键词是较为简单的词如book，远低于用户设置的目标，则应该生成简单的短句。This is a book.或This is a book.


输出格式要求：

- 必须返回严格的JSON格式，结构为：{{"sentences": [[{language}例句1, 中文翻译1], [{language}例句2, 中文翻译2], ..., [{language}例句5, 中文翻译5]]}}，不得以代码块形式输出
- 每个子数组必须包含两个字符串元素：第一个是包含关键词‘{world}’的{language}例句，第二个是对应的中文翻译
- 5个例句需覆盖关键词的各种用法和含义，且完全符合前文所述的难度/长度/学习目标要求
- **绝对不要** 输出任何其他内容，如序号、标题、解释或额外字段
- 必须以`sentences`命名变量，而不是{world}'''

# 默认格式示例 - 普通版本
DEFAULT_FORMAT_NORMAL = '''

示例JSON输出：
{{
    "sentences": [
        [
            "The research findings suggest a correlation between sleep quality and cognitive performance.",
            "研究结果表明睡眠质量与认知表现之间存在相关性。"
        ],
        [
            "Children instinctively grasp simple concepts faster than abstract theories.",
            "孩子们本能地掌握简单概念比抽象理论要快。"
        ]
    ]
}}


示例仅为格式参考。语言，难度，句子长度等信息请按照生成规则。请严格按照上述要求生成。
'''

# 默认格式示例 - 高亮版本
DEFAULT_FORMAT_HIGHLIGHT = '''
- 翻译需要自然准确，并在关键词前后，以及翻译的对应或相关部分，加上<u>标签强调显示。
示例JSON输出：
{{
    "sentences": [
        [
            "The research findings suggest a <u>correlation</u> between sleep quality and cognitive performance.",
            "研究结果表明睡眠质量与认知表现之间存在<u>相关性</u>。"
        ],
        [
            "Children <u>instinctively</u> grasp simple concepts faster than abstract theories.",
            "孩子们<u>本能地</u>掌握简单概念比抽象理论要快。"
        ]
    ]
}}


示例仅为格式参考。语言，难度，句子长度等信息请按照生成规则。请严格按照上述要求生成。
'''


# --- Configuration (can be loaded from config or passed) ---
# Default values, consider loading these dynamically
DEFAULT_CONFIG = {
    "vocab_level": "大学英语四级 CET-4 (4000词)",
    "learning_goal": "提升日常浏览英文网页与资料的流畅度",
    "difficulty_level": "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
    "sentence_length_desc": "中等长度句 (约25-40词): 通用对话及文章常用长度",
    "learning_language":"英语",
    "highlight_target_word":"默认-不标记目标词"
}

def get_prompts(config):

    custom_prompts = config.get("custom_prompts", {})
    highlight_target_word = config.get("highlight_target_word", DEFAULT_CONFIG["highlight_target_word"])
    if highlight_target_word == "默认-不标记目标词":
        prompt = DEFAULT_PROMPT_TEMPLATE + DEFAULT_FORMAT_NORMAL
    elif highlight_target_word == "默认-标记目标词":
        prompt = DEFAULT_PROMPT_TEMPLATE + DEFAULT_FORMAT_HIGHLIGHT
    else:
        custom_prompts = config.get("custom_prompts", {})
        prompt = custom_prompts.get(highlight_target_word,DEFAULT_PROMPT_TEMPLATE + DEFAULT_FORMAT_NORMAL)
    return prompt

def generate_ai_sentence(config, keyword,prompt = None):
    """
    同步调用AI接口生成包含关键词的例句。
    直接返回例句对列表（[[英文, 中文], ...]）或在出错时抛出异常。
    """
    # Merge default config with provided config if necessary, or just use provided
    api_url = config.get("api_url")
    api_key = config.get("api_key")
    model_name = config.get("model_name")
    vocab_level = config.get("vocab_level", DEFAULT_CONFIG["vocab_level"])
    learning_goal = config.get("learning_goal", DEFAULT_CONFIG["learning_goal"])
    difficulty_level = config.get("difficulty_level", DEFAULT_CONFIG["difficulty_level"])
    sentence_length_desc = config.get("sentence_length_desc", DEFAULT_CONFIG["sentence_length_desc"])
    learning_language = config.get("learning_language", DEFAULT_CONFIG["learning_language"])

    # 从配置中读取提示词模板，如果没有则使用默认值
    prompt_template = config.get("prompt_template", DEFAULT_PROMPT_TEMPLATE)
    prompt_format_normal = config.get("prompt_format_normal", DEFAULT_FORMAT_NORMAL)
    prompt_format_highlight = config.get("prompt_format_highlight", DEFAULT_FORMAT_HIGHLIGHT)

    # 根据是否高亮目标词选择不同的格式示例
    if prompt == None:
        prompt = get_prompts(config)

    formatted_prompt = prompt.format(
        world=keyword,
        vocab_level=vocab_level,
        learning_goal=learning_goal,
        difficulty_level=difficulty_level,
        sentence_length_desc=sentence_length_desc,
        language = learning_language
    )
    
    if not api_url or not api_key or not model_name:
        raise ValueError("API URL, Key, or Model Name missing in config.")
    try:
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": formatted_prompt}],
                "response_format": {"type": "json_object"}
            },
            timeout=30
        )

        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        # Parse JSON response
        try:
            response_json = response.json()
            message_content = response_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"错误：[generate_ai_sentence] 无法从API响应中提取/解析内容，关键词：'{keyword}'。错误：{e}。响应文本：{response.text[:500]}")
            #用户不应该看到报错，raise都注释掉
            #raise ValueError(f"API响应格式错误：{e}") from e

        # Parse the nested JSON content
        try:
            message_content = re.sub(r'(^```(?:[a-zA-Z0-9]+)?\s*\n|\s*```\s*$)', '', message_content, flags=re.DOTALL)
            message_content_json = json.loads(message_content)
            sentence_pairs_raw = message_content_json.get("sentences")
        except json.JSONDecodeError as e:
            sentence_pairs_raw = []
            print(f"错误：[generate_ai_sentence] API消息内容对于关键字'{keyword}'不是有效的JSON格式：{message_content[:500]}")
            #raise ValueError("API returned non-JSON content") from e


        if not isinstance(sentence_pairs_raw, list):

            print(f"错误：[generate_ai_sentence] 在关键字'{keyword}'的API响应中未找到'sentences'键或其不是列表。内容：{message_content_json}")
            #raise ValueError("API response missing 'sentences' list")

        # Convert to list of lists and validate format
        sentence_pairs = []
        for pair in sentence_pairs_raw:
            if isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str) and isinstance(pair[1], str):
                sentence_pairs.append(pair) # Store as list of lists directly
            else:
                #print(f"WARNING: [generate_ai_sentence] Skipping invalid pair format in response for '{keyword}': {pair}")
                print(f"警告：[generate_ai_sentence] 跳过关键字'{keyword}'的响应中无效的配对格式：{pair}")

        if not sentence_pairs:
            print(f"警告：[generate_ai_sentence] 在解析关键词 '{keyword}' 后未找到有效的句子对。")
            # 决定是抛出错误还是返回空列表
            # 如果API有时返回空值，返回空列表可能是可以接受的
            return [] # Return empty list if no valid pairs


        return sentence_pairs # Return list of lists [[en, cn], ...]

    except requests.exceptions.RequestException as e:
        print(f"错误：[generate_ai_sentence] 关键词 '{keyword}' 的网络错误：{e}")
        #raise ConnectionError(f"Network error: {e}") from e
    except Exception as e: # Catch other unexpected errors during the process
        #print(f"ERROR: [generate_ai_sentence] Unexpected error for keyword '{keyword}': {type(e).__name__} - {e}")
        print(f"错误：[generate_ai_sentence] 关键字 '{keyword}' 出现意外错误：{type(e).__name__} - {e}")
        traceback.print_exc()
        #raise RuntimeError(f"Unexpected error: {e}") from e

# 新的同步测试函数，替代之前的异步流式版本
def test_api_sync(
    api_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: int = 30
) -> tuple[typing.Optional[str], typing.Optional[str]]:
    """
    通过同步、非流式请求测试API连接。
    请求API重复一个简短的词。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # 简单的prompt，要求重复一个词，并限制token数量
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "不要有任何多余其他输出，重复一遍这个词: Hello"}],
        "max_tokens": 50
    }

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=timeout_seconds
        )

        if response.status_code != 200:
            error_msg_detail = "Unknown error"
            try:
                # 尝试从JSON响应中获取错误信息
                error_json = response.json()
                error_msg_detail = error_json.get("error", {}).get("message", response.text)
            except json.JSONDecodeError:
                # 如果响应不是JSON，则直接使用文本内容
                error_msg_detail = response.text
            return None, f"API错误 {response.status_code}: {error_msg_detail[:200]}" # 限制错误信息长度

        response_json = response.json()

        # 提取内容 - 这种结构对于类OpenAI的API是常见的
        # 如果目标API具有不同的响应结构，请进行调整
        if response_json.get("choices") and \
           isinstance(response_json["choices"], list) and \
           len(response_json["choices"]) > 0 and \
           response_json["choices"][0].get("message") and \
           isinstance(response_json["choices"][0]["message"], dict) and \
           response_json["choices"][0]["message"].get("content"):

            content = response_json["choices"][0]["message"]["content"]
            return content.strip(), None # 返回提取到的内容
        else:
            # 如果结构不同或内容缺失，则回退
            # 如果解析失败，尝试返回原始文本或其一部分
            # 这表明连接成功，但响应格式非预期
            return response.text[:100] if response.text else "响应为空", "响应格式非预期，但连接已建立。"

    except requests.exceptions.Timeout:
        return None, f"请求在 {timeout_seconds} 秒后超时。"
    except requests.exceptions.RequestException as e: # 其他 requests 库的异常
        return None, f"HTTP请求错误: {str(e)}"
    except json.JSONDecodeError:
        # 如果API没有返回JSON，但状态码是200，可能是纯文本
        if response and response.status_code == 200 and response.text:
             return response.text[:50], None # 返回纯文本的前50个字符
        return None, "无法从API解码JSON响应。"
    except Exception as e: # 其他意外错误
        # import traceback
        # traceback.print_exc() # 用于调试
        return None, f"发生意外错误: {str(e)}"