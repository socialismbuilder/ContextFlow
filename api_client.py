import requests
import json
import aqt
import traceback
import typing
import re
import random
from .config_manager import get_config, clean_html


class AISentenceGenerator:
    """封装提示词模板、API通信和响应解析"""

    # --- 提示词模板 ---

    DEFAULT_PROMPT_TEMPLATE = '''
你是一个学习插件的例句生成助手
请为{language}学习者生成5个包含关键词 '{world}' 的{language}例句，并附带中文翻译。

学习者信息：
- 当前词汇量大致为：{vocab_level}
- 学习目标是：{learning_goal}
- 句子最大难度：{difficulty_level}
- 句子最大长度:{sentence_length_desc}

例句生成规则：
- 提供的关键词 '{world}' 是一个完整的词汇/短语。它可以是原形、复数、过去式等屈折形式，或作为组合词的一部分，但不能是该词根衍生的其他词汇。
（例如，如果关键词是 "book"，例句中可以使用 "books" 或 "notebook" 中的 "book" 部分，前提是notebook的book代表着原本含义）
- 绝对禁止将关键词用作前后缀来构成一个不同的词汇，或使用与关键词同根但意义完全不同的衍生词。
（例如，给出关键词book,例句不能使用booking;给出king，例句不能使用kingdom）
- 若关键词是用括号注释了某一个翻译的多义词，则例句中只能使用该翻译对应的含义。
- 语境应尽量与学习目标 ({learning_goal}) 相关，或者为通用场景。
- 每个例句必须包含关键词 '{world}'。
{second_keywords}
- - 第二关键词的加入顺势而为，不限制是否加入或加入几个，请以句子自然流畅符合逻辑，不能为了加入而破坏句子的合理性
- 5个例句应尽量全面的覆盖关键词的各种用法和含义。
- 例句和翻译必须分别是单一语言，不得双语混杂，不要被括号中的注释影响。

输出格式要求：

- 必须返回严格的JSON格式，结构为：{{"sentences": [[{language}例句1, 中文翻译1], [{language}例句2, 中文翻译2], ..., [{language}例句5, 中文翻译5]]}}，不得以代码块形式输出
- 每个子数组必须包含两个字符串元素：第一个是包含关键词'{world}'的{language}例句，第二个是对应的中文翻译
- 5个例句需覆盖关键词的各种用法和含义，且完全符合前文所述的难度/长度/学习目标要求
- **绝对不要** 输出任何其他内容，如序号、标题、解释或额外字段
- 必须以`sentences`命名变量，而不是{world}'''

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

    DEFAULT_CONFIG = {
        "vocab_level": "大学英语四级 CET-4 (4000词)",
        "learning_goal": "提升日常浏览英文网页与资料的流畅度",
        "difficulty_level": "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
        "sentence_length_desc": "中等长度句 (约25-40词): 通用对话及文章常用长度",
        "learning_language": "英语",
        "prompt_name": "默认-不标记目标词"
    }

    def __init__(self):
        self.support_thinking: bool = True
        self._top_difficulty_keywords: list = []

    # --- 提示词管理 ---

    def get_prompts(self, config):
        custom_prompts = config.get("custom_prompts", {})
        prompt_name = config.get("prompt_name", self.DEFAULT_CONFIG["prompt_name"])
        if prompt_name == "默认-不标记目标词":
            prompt = self.DEFAULT_PROMPT_TEMPLATE + self.DEFAULT_FORMAT_NORMAL
        elif prompt_name == "默认-标记目标词":
            prompt = self.DEFAULT_PROMPT_TEMPLATE + self.DEFAULT_FORMAT_HIGHLIGHT
        else:
            custom_prompts = config.get("custom_prompts", {})
            prompt = custom_prompts.get(prompt_name, self.DEFAULT_PROMPT_TEMPLATE + self.DEFAULT_FORMAT_NORMAL)
        return prompt

    def format_prompt(self, config, keyword, prompt=None):
        """构建格式化后的提示词字符串"""
        config_second_kw_enabled = config.get("second_keywords_enabled", True)
        config_second_kw_top_n = config.get("second_keywords_top_n", 100)

        if config_second_kw_enabled:
            if not self._top_difficulty_keywords:
                self._top_difficulty_keywords = self.get_top_difficulty_keywords()

            if not self._top_difficulty_keywords or len(self._top_difficulty_keywords) < config_second_kw_top_n:
                second_keywords_str = ""
            else:
                second_keywords = random.sample(self._top_difficulty_keywords, 10) if len(
                    self._top_difficulty_keywords) >= 10 else self._top_difficulty_keywords
                second_keywords_str = ", ".join(second_keywords)
                second_keywords_str = "- 在保证句子流畅的前提下，可以在每个例句中尝试融入若干以下词汇(" + second_keywords_str + ")，不限制每句融入几个，不得强制融入牺牲流传性，0-3个为佳，必须以句子自然流畅为前提。"
        else:
            second_keywords_str = ""

        vocab_level = config.get("vocab_level", self.DEFAULT_CONFIG["vocab_level"])
        learning_goal = config.get("learning_goal", self.DEFAULT_CONFIG["learning_goal"])
        difficulty_level = config.get("difficulty_level", self.DEFAULT_CONFIG["difficulty_level"])
        sentence_length_desc = config.get("sentence_length_desc", self.DEFAULT_CONFIG["sentence_length_desc"])
        learning_language = config.get("learning_language", self.DEFAULT_CONFIG["learning_language"])

        if prompt is None:
            prompt = self.get_prompts(config)

        return prompt.format(
            world=keyword,
            vocab_level=vocab_level,
            learning_goal=learning_goal,
            difficulty_level=difficulty_level,
            sentence_length_desc=sentence_length_desc,
            language=learning_language,
            second_keywords=second_keywords_str
        )

    # --- 高层生成 ---

    def generate(self, config, keyword, prompt=None):
        """同步调用AI接口生成包含关键词的例句，返回例句对列表"""
        formatted_prompt = self.format_prompt(config, keyword, prompt)

        try:
            response = self.get_api_response(config, formatted_prompt)
            message_content = self.get_message_content(response, keyword)
            sentence_pairs = self.parse_response(message_content, keyword)
            if not sentence_pairs:
                return []
            return sentence_pairs
        except Exception as e:
            print(f"错误：[generate] 关键字 '{keyword}' 出现意外错误：{type(e).__name__} - {e}")
            traceback.print_exc()
            return []

    # --- API通信 ---

    def get_api_response(self, config, formatted_prompt):
        api_url = config.get("api_url")
        api_key = config.get("api_key")
        model_name = config.get("model_name")
        try:
            final_prompt = formatted_prompt
            if model_name and "qwen3" in model_name.lower():
                final_prompt = formatted_prompt + "/no_think"

            if self.support_thinking:
                response = requests.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": final_prompt}],
                        "thinking": {"type": "disabled"}
                    },
                    timeout=30
                )
            else:
                response = requests.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": final_prompt}],
                    },
                    timeout=30
                )

            if response.status_code != 200:
                try:
                    error_json = response.json()
                    error_msg_detail = error_json.get("error", {}).get("message", response.text)
                    if 'thinking' in error_msg_detail.lower():
                        self.support_thinking = False
                        _sync_support_thinking(False)
                except:
                    pass

            return response
        except requests.exceptions.RequestException as e:
            print(f"错误：[get_api_response] 网络错误：{e}")
            return None
        except Exception as e:
            print(f"错误：[get_api_response] 意外错误：{type(e).__name__} - {e}")
            return None

    @staticmethod
    def get_message_content(response, keyword):
        if response is None:
            return ""
        if response.status_code != 200:
            try:
                error_json = response.json()
                error_msg_detail = error_json.get("error", {}).get("message", response.text)
                if 'thinking' in error_msg_detail.lower():
                    _sync_support_thinking(False)
                    return f"API不支持thinking参数，已禁用thinking参数，请重新尝试。错误详情：{error_msg_detail}"
            except:
                pass
        try:
            response_json = response.json()
            message_content = response_json["choices"][0]["message"]["content"]
            return message_content
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(
                f"错误：[get_message_content] 无法从API响应中提取/解析内容，关键词：'{keyword}'。错误：{e}。响应文本：{response.text[:500]}")
            return ""

    @staticmethod
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

    # --- 难度关键词 ---

    def get_top_difficulty_keywords(self):
        """返回学过的单词中难度排名前N的关键词列表，N由配置决定"""
        config = get_config()
        try:
            deck_name = config.get("deck_name")
            if not deck_name:
                print("ERROR: 未获取到有效牌组名称")
                return []

            query = f"deck:{deck_name} is:review prop:d>=0.6"
            card_ids = aqt.mw.col.find_cards(query)
            if not card_ids:
                print("INFO: 牌组中无符合条件的复习卡片")
                return []

            difficulty_keywords = []
            for cid in card_ids:
                card = aqt.mw.col.get_card(cid)
                try:
                    raw_keyword = card.note().fields[0] if card.note().fields else ""
                    keyword = clean_html(raw_keyword)
                    if not keyword:
                        continue

                    if card.memory_state is None:
                        continue
                    difficulty = card.memory_state.difficulty

                    difficulty_keywords.append((difficulty, keyword))
                except Exception as e:
                    print(f"ERROR: 处理卡片{cid}时出错: {str(e)}")
                    continue

            difficulty_keywords.sort(reverse=True, key=lambda x: x[0])
            top_n = config.get("second_keywords_top_n", 100)
            top_keywords = [kw for (diff, kw) in difficulty_keywords[:top_n]]
            return top_keywords

        except Exception as e:
            print(f"ERROR: 获取难度排名关键词失败: {str(e)}")
            return []

    def clear_cache(self):
        """清除第二关键词缓存，使配置变更立即生效"""
        self._top_difficulty_keywords = []

    # --- 模型列表 ---

    @staticmethod
    def fetch_available_models(api_url: str, api_key: str) -> list:
        if not api_url or not api_key:
            return []

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

        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
            return models
        except Exception as e:
            print(f"错误：[fetch_available_models] 获取模型列表失败: {e}")
            return []

    # --- 连接测试 ---

    def test_connection(self, api_url: str, api_key: str, model_name: str,
                        timeout_seconds: int = 30) -> tuple:
        test_prompt = "不要有任何多余其他输出，重复一遍这个词: Hello"
        if model_name and "qwen3" in model_name.lower():
            test_prompt = test_prompt + "/no_think"

        if not self.support_thinking:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": test_prompt}],
                "max_tokens": 50
            }
        else:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": test_prompt}],
                "max_tokens": 50,
                "thinking": {"type": "disabled"}
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
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
                    error_json = response.json()
                    error_msg_detail = error_json.get("error", {}).get("message", response.text)
                    if 'thinking' in error_msg_detail.lower():
                        self.support_thinking = False
                        _sync_support_thinking(False)
                        error_msg_detail = "API不支持thinking参数，已禁用思考，请重新尝试。"
                except json.JSONDecodeError:
                    error_msg_detail = response.text
                return None, f"API错误 {response.status_code}: {error_msg_detail[:200]}"

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

        except requests.exceptions.Timeout:
            return None, f"请求在 {timeout_seconds} 秒后超时。"
        except requests.exceptions.RequestException as e:
            return None, f"HTTP请求错误: {str(e)}"
        except json.JSONDecodeError:
            if response and response.status_code == 200 and response.text:
                return response.text[:50], None
            return None, "无法从API解码JSON响应。"
        except Exception as e:
            return None, f"发生意外错误: {str(e)}"


# --- 单例实例 ---
_generator = AISentenceGenerator()


def _sync_support_thinking(value):
    """同步模块级别的 support_thinking 变量"""
    global support_thinking
    support_thinking = value


# --- 向后兼容的模块级常量 ---
DEFAULT_PROMPT_TEMPLATE = AISentenceGenerator.DEFAULT_PROMPT_TEMPLATE
DEFAULT_FORMAT_NORMAL = AISentenceGenerator.DEFAULT_FORMAT_NORMAL
DEFAULT_FORMAT_HIGHLIGHT = AISentenceGenerator.DEFAULT_FORMAT_HIGHLIGHT
DEFAULT_CONFIG = AISentenceGenerator.DEFAULT_CONFIG
support_thinking = True


# --- 向后兼容的模块级函数 ---
def generate_ai_sentence(config, keyword, prompt=None):
    return _generator.generate(config, keyword, prompt)


def get_prompts(config):
    return _generator.get_prompts(config)


def get_api_response(config, formatted_prompt):
    return _generator.get_api_response(config, formatted_prompt)


def get_message_content(response, keyword):
    return AISentenceGenerator.get_message_content(response, keyword)


def parse_message_content_to_sentence_pairs(message_content, keyword):
    return AISentenceGenerator.parse_response(message_content, keyword)


def get_top_difficulty_keywords():
    return _generator.get_top_difficulty_keywords()


def fetch_available_models(api_url: str, api_key: str) -> list:
    return AISentenceGenerator.fetch_available_models(api_url, api_key)


def test_api_sync(api_url: str, api_key: str, model_name: str,
                  timeout_seconds: int = 30) -> tuple:
    return _generator.test_connection(api_url, api_key, model_name, timeout_seconds)
