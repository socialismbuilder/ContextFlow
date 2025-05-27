import requests
import json
import aqt
import concurrent.futures
import traceback
import typing # Add typing for Optional
import re
import random
from .config_manager import get_config
import html
top_difficulty_keywords = []
# Configuration details are dynamically loaded from user settings via config_manager

# 默认提示词模板 - 现在从配置中读取
DEFAULT_PROMPT_TEMPLATE = '''
你是一个学习插件的例句生成助手
请为{language}学习者生成5个包含关键词 ‘{world}’ 的{language}例句，并附带中文翻译。

学习者信息：
- 当前词汇量大致为：{vocab_level}
- 学习目标是：{learning_goal}
- 句子最大难度：{difficulty_level}
- 句子最大长度:{sentence_length_desc}

例句生成规则：
- 难度控制原则：评估关键词 '{world}' 的固有难度，与设定的目标句子难度，生成的句子整体难度必须同时低于关键词的固有难度和设定的目标难度。
例如：如果关键词是较为简单的词如book，远低于用户设置的目标，则应该生成简单的短句。This is a book.或This is a book.
- 提供的关键词 '{world}' 是一个完整的词汇。它可以是原形、复数、过去式等屈折形式，或作为组合词的一部分，但不能是该词根衍生的其他词汇。
（例如，如果关键词是 "book"，例句中可以使用 "books" 或 "notebook" 中的 "book" 部分，前提是notebook的book代表着原本含义）
- 绝对禁止将关键词用作前后缀来构成一个不同的词汇，或使用与关键词同根但意义完全不同的衍生词。
（例如，给出关键词book,例句不能使用booking;给出king，例句不能使用kingdom）
- 语境应尽量与学习目标 ({learning_goal}) 相关，或者为通用场景。
- 每个例句必须包含关键词 ‘{world}’。
{second_keywords}
- 5个例句应尽量全面的覆盖关键词的各种用法和含义。

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
    "prompt_name":"默认-不标记目标词"
}

def get_prompts(config):

    custom_prompts = config.get("custom_prompts", {})
    prompt_name = config.get("prompt_name", DEFAULT_CONFIG["prompt_name"])
    if prompt_name == "默认-不标记目标词":
        prompt = DEFAULT_PROMPT_TEMPLATE + DEFAULT_FORMAT_NORMAL
    elif prompt_name == "默认-标记目标词":
        prompt = DEFAULT_PROMPT_TEMPLATE + DEFAULT_FORMAT_HIGHLIGHT
    else:
        custom_prompts = config.get("custom_prompts", {})
        prompt = custom_prompts.get(prompt_name,DEFAULT_PROMPT_TEMPLATE + DEFAULT_FORMAT_NORMAL)
    return prompt

def clean_html(raw_string):
    """
    清洗 HTML 内容，包括：
    1. 移除所有 HTML 标签
    2. 移除方括号内容（如 [sound:...]）
    3. 解码 HTML 实体（如 &nbsp; -> 空格）
    4. 去除首尾空格
    """
    no_html = re.sub(r'<.*?>', '', raw_string)
    no_sound = re.sub(r'\[.*?\]', '', no_html)
    decoded = html.unescape(no_sound)
    cleaned = decoded.strip()
    return cleaned

# 新增难度排名前100关键词的函数
def get_top_difficulty_keywords():
    """返回学过的单词中难度排名前100的关键词列表（难度根据容易度因子逆序计算）"""
    config = get_config()
    try:
        # 获取目标牌组名称
        deck_name = config.get("deck_name")  # 从配置获取牌组ID对应的名称
        if not deck_name:
            print("ERROR: 未获取到有效牌组名称")
            return []

        # 查询条件：目标牌组中复习且难度≥0.6的卡片（用户要求）
        query = f"deck:{deck_name} is:review prop:d>=0.6"
        card_ids = aqt.mw.col.find_cards(query)
        if not card_ids:
            print("INFO: 牌组中无符合条件的复习卡片")
            return []

        # 获取所有卡片对象并提取FSRS难度信息
        difficulty_keywords = []
        for cid in card_ids:
            card = aqt.mw.col.get_card(cid)
            try:
                # 获取关键词（清理HTML）
                raw_keyword = card.note().fields[0] if card.note().fields else ""
                keyword = clean_html(raw_keyword)
                if not keyword:
                    continue

                # 获取FSRS记忆状态中的难度值（根据用户提供的类结构）
                if card.memory_state is None:
                    continue  # 跳过无记忆状态的卡片
                difficulty = card.memory_state.difficulty

                difficulty_keywords.append( (difficulty, keyword) )
            except Exception as e:
                print(f"ERROR: 处理卡片{cid}时出错: {str(e)}")
                continue

        # 按难度降序排序（难度越高越靠前），取前100个
        difficulty_keywords.sort(reverse=True, key=lambda x: x[0])
        top_keywords = [kw for (diff, kw) in difficulty_keywords[:100]]
        return top_keywords

    except Exception as e:
        print(f"ERROR: 获取难度排名关键词失败: {str(e)}")
        return []


def get_api_response(config,formatted_prompt):
    api_url = config.get("api_url")
    api_key = config.get("api_key")
    model_name = config.get("model_name")
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
        return response
    #出现异常print出来
    except requests.exceptions.RequestException as e:
        print(f"错误：[get_api_response] 网络错误：{e}")
        return None
    except Exception as e: # Catch other unexpected errors during the process
        print(f"错误：[get_api_response] 意外错误：{type(e).__name__} - {e}")
        return None

def get_message_content(response,keyword):
    if response is None:
        return ""
    try:
        response_json = response.json()
        message_content = response_json["choices"][0]["message"]["content"]
        return message_content
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"错误：[get_message_content] 无法从API响应中提取/解析内容，关键词：'{keyword}'。错误：{e}。响应文本：{response.text[:500]}")
        return ""
        #用户不应该看到报错，raise都注释掉
        #raise ValueError(f"API响应格式错误：{e}") from e

def parse_message_content_to_sentence_pairs(message_content: str, keyword: str) -> list:
    """
    将API返回的message_content解析为句子对列表[[语言例句, 中文翻译], ...]
    :param message_content: API返回的原始消息内容
    :param keyword: 当前处理的关键词（用于错误提示）
    :return: 有效的句子对列表，空列表表示无有效数据
    """
    # 清理可能的代码块标记
    try:
        cleaned_content = re.sub(r'(^```(?:[a-zA-Z0-9]+)?\s*\n|\s*```\s*$)', '', message_content, flags=re.DOTALL)
        content_json = json.loads(cleaned_content)
        raw_pairs = content_json.get("sentences")
    except json.JSONDecodeError:
        print(f"错误：[parse_message_content_to_sentence_pairs] 关键字'{keyword}'的响应非JSON格式：{message_content[:200]}")
        return []
    
    # 验证sentences字段类型
    if not isinstance(raw_pairs, list):
        print(f"错误：[parse_message_content_to_sentence_pairs] 关键字'{keyword}'未找到有效sentences列表")
        return []
    
    # 验证每个句子对格式
    valid_pairs = []
    for pair in raw_pairs:
        if isinstance(pair, list) and len(pair) == 2 and all(isinstance(item, str) for item in pair):
            valid_pairs.append(pair)
        else:
            print(f"警告：[parse_message_content_to_sentence_pairs] 关键字'{keyword}'跳过无效配对：{pair}")
    
    if not valid_pairs:
        print(f"警告：[parse_message_content_to_sentence_pairs] 关键字'{keyword}'未找到有效句子对")
    
    return valid_pairs


def generate_ai_sentence(config, keyword,prompt = None):
    """
    同步调用AI接口生成包含关键词的例句。
    直接返回例句对列表（[[英文, 中文], ...]）或在出错时抛出异常。
    """
    # 初始化难度关键词列表（全局变量）
    global top_difficulty_keywords
    if not top_difficulty_keywords:  # 列表为空时获取最新数据
        top_difficulty_keywords = get_top_difficulty_keywords()
    if not top_difficulty_keywords:
        second_keywords_str = ""
    else:
        # 随机选取10个作为第二关键词（不足10个则全选）
        second_keywords = random.sample(top_difficulty_keywords, 10) if len(top_difficulty_keywords)>=10 else top_difficulty_keywords
        # 转换为逗号分隔的字符串格式
        second_keywords_str = ", ".join(second_keywords)
        second_keywords_str = "- 在保证句子流畅的前提下，可以在每个例句中尝试融入若干以下词汇（"+second_keywords_str+"），不限制每句融入几个，也不强制融入，但必须以句子自然流畅为前提。"

    vocab_level = config.get("vocab_level", DEFAULT_CONFIG["vocab_level"])
    learning_goal = config.get("learning_goal", DEFAULT_CONFIG["learning_goal"])
    difficulty_level = config.get("difficulty_level", DEFAULT_CONFIG["difficulty_level"])
    sentence_length_desc = config.get("sentence_length_desc", DEFAULT_CONFIG["sentence_length_desc"])
    learning_language = config.get("learning_language", DEFAULT_CONFIG["learning_language"])

    # 没有输入prompt则执行获取prompt函数
    if prompt == None:
        prompt = get_prompts(config)

    formatted_prompt = prompt.format(
        world=keyword,
        vocab_level=vocab_level,
        learning_goal=learning_goal,
        difficulty_level=difficulty_level,
        sentence_length_desc=sentence_length_desc,
        language = learning_language,
        second_keywords=second_keywords_str
    )
    #print("格式化提示词")
    #print(second_keywords_str)

    try:
        response = get_api_response(config,formatted_prompt)
        message_content = get_message_content(response, keyword)
        sentence_pairs = parse_message_content_to_sentence_pairs(message_content, keyword)
        if not sentence_pairs:
            return [] # Return empty list if no valid pairs

        return sentence_pairs # Return list of lists [[en, cn], ...]

    except Exception as e: # Catch other unexpected errors during the process
        print(f"错误：[generate_ai_sentence] 关键字 '{keyword}' 出现意外错误：{type(e).__name__} - {e}")
        traceback.print_exc()



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
