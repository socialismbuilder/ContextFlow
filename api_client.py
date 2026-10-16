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

    DEFAULT_PROMPT_TEMPLATE = '''你是一个专业的{language}学习助手。请为学习者生成 5 个包含目标词 '{world}' 的高质量例句，并提供准确的中文翻译。

【学习者设定与要求】
- 目标词汇量：{vocab_level}
- 学习目标：{learning_goal}
- 句子难度：{difficulty_level}
- 句子长度：{sentence_length_desc}

【例句生成准则】
1. 词形形态：每句必须包含目标词 '{world}'。允许使用自然的屈折变化（如时态、复数），但严禁使用派生衍生词（例如：词为 book 时不可用 booking，king 不可用 kingdom）。
2. 词义限定：若目标词带有括号注释（如多义词指定义项），例句必须严格限定在该注释对应的含义。
3. 语境分布：5个例句应尽量展示该词在符合学习目标语境下的不同典型用法或常见搭配。
4. 语言纯粹：例句必须是纯{language}，翻译必须是纯中文，严禁双语夹杂。{second_keywords}

【输出格式要求】
- 必须直接输出纯 JSON，严禁使用 Markdown 代码块（如 ```json），严禁输出任何问候、解释、序号或额外字段。
- 顶层必须是以 "sentences" 为键的对象，包含 5 个子数组，格式如下：
{{"sentences": [
  ["{language}例句1", "中文翻译1"],
  ...
  ["{language}例句5", "中文翻译5"]
]}}'''

    DEFAULT_FORMAT_NORMAL = '''

【输出示例】
{{
  "sentences": [
    [
      "The research findings suggest a clear correlation between sleep quality and cognitive performance.",
      "研究结果表明，睡眠质量与认知表现之间存在明显的关联。"
    ],
    [
      "Children instinctively grasp simple concepts faster than abstract theories.",
      "孩子们本能地掌握简单概念比抽象理论要快。"
    ]
  ]
}}

请严格按照上述要求与示例格式直接输出纯 JSON。'''

    DEFAULT_FORMAT_HIGHLIGHT = '''

【高亮标记规范（极其重要，必须严格执行）】
1. 目标词与屈折整体标记：英文例句中必须使用 <u>...</u> 标记目标词；其屈折变化形式（如时态、复数）必须整体包裹在标签内（如 <u>mills</u>、<u>strolled</u>）。
2. 固定短语整体包裹：若目标词与相邻词构成了固定短语、搭配或成语（如 "For example", "water mill", "take care of" 等），必须将【整个短语作为整体】用 <u>...</u> 包裹（例如必须标为 <u>For example</u>，严禁标成 For <u>example</u>）。
3. 汉英双向对齐：中文翻译中对应目标词或固定短语的含义部分，【必须且只能】使用 <u>...</u> 严格对应标记（例如 <u>For example</u> 对应 <u>例如</u>，<u>water mill</u> 对应 <u>水磨</u>）。
4. 严禁单端漏标：每组例句和翻译必须有且仅有对应的高亮标记，绝对禁止单侧遗漏（严禁英文标了中文没标，或中文标了英文没标）！

【输出示例】
{{
  "sentences": [
    [
      "<u>For example</u>, you can find a hidden carousel in the casino area of the game.",
      "<u>例如</u>，你可以在游戏的赌场区域找到一个隐藏的旋转木马。"
    ],
    [
      "The research findings suggest a clear <u>correlation</u> between sleep quality and cognitive performance.",
      "研究结果表明，睡眠质量与认知表现之间存在明显的<u>相关性</u>。"
    ],
    [
      "In this workshop, you can use the <u>water mill</u> to generate power for your base.",
      "在这个工坊里，你可以使用<u>水磨</u>为你的基地发电。"
    ]
  ]
}}

请严格按照上述要求与高亮规范直接输出纯 JSON。'''

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
                second_keywords_str = "\n5. 拓展融入：在保证句子自然流畅的前提下，可顺势在例句中融入以下词汇中的 0-3 个（非强制，以自然流畅为先）：" + second_keywords_str
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
