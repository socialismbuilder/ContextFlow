# -*- coding: utf-8 -*-
"""
提示词统一管理模块。

职责：
- 例句生成提示词模板（默认模板 + 普通/高亮格式段）
- AI 解释对话提示词（桌面端 / Web 端共用）
- 提示词占位符填充（format_prompt / build_prompt）
- 第二关键词数据源（Anki 牌组难度 Top-N）

本模块只负责"提示词"，不负责任何网络请求；
LLM 调用见 llm_client.py，例句生成编排见 sentence_service.py。
"""

import random

import aqt

from .config_manager import get_config, clean_html


# ============================================================
# 例句生成提示词
# ============================================================

# 提示词占位符一览（提示词编辑器帮助文案也引用此表）
SENTENCE_PROMPT_PLACEHOLDERS = {
    "world": "关键词",
    "language": "学习语言",
    "vocab_level": "词汇量等级",
    "learning_goal": "学习目标",
    "difficulty_level": "句子难度",
    "sentence_length_desc": "句子长度",
    "second_keywords": "第二关键词",
}

SENTENCE_PROMPT_TEMPLATE = '''你是一个专业的{language}学习助手。请为学习者生成 5 个包含目标词 '{world}' 的高质量例句，并提供准确的中文翻译。

【学习者设定与要求】
- 目标词汇量：{vocab_level}
- 学习目标：{learning_goal}
- 句子难度：{difficulty_level}
- 句子长度：{sentence_length_desc}

【例句生成准则】
1. 词形形态：每句必须包含目标词 '{world}'。允许使用自然的屈折变化（如时态、复数），也允许它以固定短语或复合词的一部分出现（例如词为 book 时，books、notebook 中作"书"讲的 book 均可用）。
2. 严禁派生：绝对禁止使用与目标词同根但含义不同的派生词（例如词为 book 时不可用 booking，词为 king 时不可用 kingdom）。
3. 词义限定：若目标词带有括号注释（如多义词指明义项），例句必须严格限定在该注释对应的含义，且输出中不要保留注释文字。
4. 语境分布：5 个例句应尽量展示该词的不同典型用法与常见搭配，语境尽量贴合学习目标；若该词不适合学习目标语境，可用通用场景，不得生搬硬套。
5. 语言纯粹：例句必须是纯{language}，翻译必须是纯中文，严禁双语夹杂。5 个例句必须同时满足上述难度、长度与学习目标要求。{second_keywords}

【输出格式要求】
- 必须直接输出纯 JSON，严禁使用 Markdown 代码块（如 ```json），严禁输出任何问候、解释、序号或额外字段。
- 顶层必须是以 "sentences" 为键的对象，包含 5 个子数组；每个子数组含两个字符串，第一个是包含目标词 '{world}' 的{language}例句，第二个是它的中文翻译。
- 结构示例如下：
{{"sentences": [
  ["{language}例句1", "中文翻译1"],
  ...
  ["{language}例句5", "中文翻译5"]
]}}'''

FORMAT_NORMAL = '''

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

示例仅为格式参考，语言，难度，句子长度等信息请按照生成规则。请严格按照上述要求与示例格式直接输出纯 JSON。'''

FORMAT_HIGHLIGHT = '''

【高亮标记规范（极其重要，必须严格执行）】
1. 目标词与屈折整体标记：{language}例句中必须使用 <u>...</u> 标记目标词（标签必须成对闭合）；其屈折变化形式（如时态、复数）必须整体包裹在标签内（如 <u>mills</u>、<u>strolled</u>）。
2. 固定短语整体包裹：若目标词与相邻词构成了固定短语、搭配或成语（如 "For example", "water mill", "take care of" 等），必须将【整个短语作为整体】用 <u>...</u> 包裹（例如必须标为 <u>For example</u>，严禁标成 For <u>example</u>）。
3. 汉英双向对齐：中文翻译中对应目标词或固定短语的含义部分，【必须且只能】使用 <u>...</u> 严格对应标记（例如 <u>For example</u> 对应 <u>例如</u>，<u>water mill</u> 对应 <u>水磨</u>）。
4. 严禁单端漏标：每组例句和翻译必须有且仅有对应的高亮标记，绝对禁止单侧遗漏（严禁{language}标了中文没标，或中文标了{language}没标）！同一句中该词/短语若出现多次，每一处都要标记。
5. 只标目标词：只标记目标词本身（含其屈折形式，或与它组成的固定短语），严禁标记例句中其他无关的常用词、连接词或短语。
6. 若提示词包含了拓展融入部分，*严禁*高亮拓展部分词汇，只标记目标词及其对应的翻译部分。

【输出示例】
{{
  "sentences": [
    [
      "The old <u>mills</u> by the river have been turned into museums.",
      "河边的那些老<u>磨坊</u>已被改建成博物馆。"
    ],
    [
      "In this workshop, you can use the <u>water mill</u> to generate power for your base.",
      "在这个工坊里，你可以使用<u>水磨</u>为你的基地发电。"
    ]
  ]
}}

示例仅为格式参考，语言，难度，句子长度等信息请按照生成规则。请严格按照上述要求与高亮规范直接输出纯 JSON。'''

# "拓展融入"第二关键词片段模板：{keywords} 为逗号分隔的词表
SECOND_KEYWORDS_SNIPPET = ("\n6. 拓展融入：在保证句子自然流畅的前提下，可顺势在例句中融入以下词汇中的 "
                           "0-3 个（非强制，以自然流畅为先）：{keywords}")

# 提示词编辑器测试用的固定第二关键词样例（仅供预览效果，不参与真实生成）
SAMPLE_SECOND_KEYWORDS = "strand,exasperated,grudgingly,guerrilla,parish,extent,casino,carousel,hypocritical,hunch"

# 提示词相关默认配置（全项目唯一一份，其他模块从这里取）
DEFAULT_CONFIG = {
    "vocab_level": "大学英语四级 CET-4 (4000词)",
    "learning_goal": "提升日常浏览英文网页与资料的流畅度",
    "difficulty_level": "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
    "sentence_length_desc": "中等长度句 (约25-40词): 通用对话及文章常用长度",
    "learning_language": "英语",
    "prompt_name": "默认-不标记目标词"
}

# 内置提示词名称
PROMPT_NAME_NORMAL = "默认-不标记目标词"
PROMPT_NAME_HIGHLIGHT = "默认-标记目标词"

# ---- 第二关键词（Anki 牌组难度 Top-N）缓存 ----
_top_difficulty_keywords: list = []


def get_prompts(config):
    """按配置中的 prompt_name 返回原始（未填充）提示词模板"""
    prompt_name = config.get("prompt_name", DEFAULT_CONFIG["prompt_name"])
    if prompt_name == PROMPT_NAME_HIGHLIGHT:
        return SENTENCE_PROMPT_TEMPLATE + FORMAT_HIGHLIGHT
    if prompt_name == PROMPT_NAME_NORMAL:
        return SENTENCE_PROMPT_TEMPLATE + FORMAT_NORMAL
    custom_prompts = config.get("custom_prompts", {})
    return custom_prompts.get(prompt_name, SENTENCE_PROMPT_TEMPLATE + FORMAT_NORMAL)


def build_second_keywords_snippet(config, sample=False):
    """构建"拓展融入"片段。sample=True 时返回固定样例（提示词编辑器预览用）。"""
    if sample:
        return SECOND_KEYWORDS_SNIPPET.format(keywords=SAMPLE_SECOND_KEYWORDS)

    enabled = config.get("second_keywords_enabled", True)
    top_n = config.get("second_keywords_top_n", 100)
    if not enabled:
        return ""

    global _top_difficulty_keywords
    if not _top_difficulty_keywords:
        _top_difficulty_keywords = get_top_difficulty_keywords()

    if not _top_difficulty_keywords or len(_top_difficulty_keywords) < top_n:
        return ""

    keywords = (random.sample(_top_difficulty_keywords, 10)
                if len(_top_difficulty_keywords) >= 10
                else _top_difficulty_keywords)
    return SECOND_KEYWORDS_SNIPPET.format(keywords=", ".join(keywords))


def format_prompt(config, keyword, prompt=None, sample_second_keywords=False):
    """构建格式化后的例句生成提示词字符串"""
    if prompt is None:
        prompt = get_prompts(config)

    return prompt.format(
        world=keyword,
        vocab_level=config.get("vocab_level", DEFAULT_CONFIG["vocab_level"]),
        learning_goal=config.get("learning_goal", DEFAULT_CONFIG["learning_goal"]),
        difficulty_level=config.get("difficulty_level", DEFAULT_CONFIG["difficulty_level"]),
        sentence_length_desc=config.get("sentence_length_desc", DEFAULT_CONFIG["sentence_length_desc"]),
        language=config.get("learning_language", DEFAULT_CONFIG["learning_language"]),
        second_keywords=build_second_keywords_snippet(config, sample=sample_second_keywords),
    )


def get_top_difficulty_keywords():
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


def clear_second_keywords_cache():
    """清除第二关键词缓存，使配置变更立即生效"""
    global _top_difficulty_keywords
    _top_difficulty_keywords = []


# ============================================================
# AI 解释对话提示词（桌面端对话框 / Web 端共用）
# ============================================================

EXPLANATION_PROMPT = """你是ContextFlow软件的语言学习助手，你将扮演一位资深的语言学家和友善的语言导师。你的任务是为语言学习者提供精准、简洁且高度相关的词汇/短语解释。

{examples_length_clause}
你的核心原则是**灵活应变**。你需要首先判断用户输入的类型，然后选择最合适的解释策略，而不是死板地遵循一个固定模板。

# 用户输入：
- 原始例句: '{sentence}'
- 目标内容: '{word_to_explain}'

# 你的工作流程：

### 第一步：智能分析
在生成回答前，请先在内部完成以下思考：
1.  **判断输入类型**: 用户选中的 `{word_to_explain}` 是一个标准的【单词】、一个【固定短语/成语】、一个【语法结构】、一个【句子片段】，还是一个可能因不理解而产生的【错误组合】（例如，选中了“我是个老师”里的“个老”）？
2.  **确定解释重点**: 基于你的判断，决定解释的侧重点。目标是解决用户最根本的困惑，而不是机械地填充所有栏目。

### 第二步：生成解释卡片
请根据你的分析，**参考**使用以下最相关的模块，组合成一份清晰易懂的学习卡片。
对于不必要或不相关的模块，请**直接省略**。
对于你觉得非常有必要的，也可以***自行添加**。
请使用 Markdown 格式化你的回答。

---

#### 📌 核心解释
- **永远需要。** 针对选中的 `{word_to_explain}` 给出最核心的定义。
- 如果是**单词**，提供词性、拼音和基本含义。
- 如果是**短语或句子**，解释其整体意思。
- 这部分讲解请无视例句中的语境，直接针对词汇/短语本身进行解释，以确保用户能建立正确的基本概念。
- 对于多义词，请给出全面的解释，并以词语的大类和引申义为主线分类，将大意类似或可以通过引申理解的归为一类，而不是根据刻板的词性和词典翻译。

#### 🌐 语境解析
- **大多数情况需要。** 解释 `{word_to_explain}` 在原句 `{sentence}` 中的具体作用和含义。

#### ✨ 用法辨析与扩展
- **（如果适用且有价值）** 提供近义词、反义词、形近词的辨析，或介绍相关的常见搭配、语法结构。**如果没有高质量的辨析内容，请跳过此项，保持简洁。**

#### 🔍 特别提醒 / 结构分析
- **（当判断为错误选择或复杂结构时使用）** 温和地指出这可能不是一个常规的词汇单位，并分解解释其组成部分。
- **例如**: 对于“个老”，应分别解释“个”（量词）和“老师”（名词），并说明正确的句子结构是“（一）个老师”。这能直接解决用户的根本困惑。

---

{examples_section}

你的回答应该像一位经验丰富的老师，既有深度，又懂得因材施教，直击要点。现在，请根据这个新的指导原则，为用户服务。

完成以上步骤后，等待用户的追问。对于随后的追问，不必遵循上述流程，完全灵活的处理。

{examples_tool_clause}
"""

# 例句生成段（含 JSON 输出要求）。web 端不启用时整段省略。
_EXAMPLES_SECTION = """### 第三步：应用实例
最后，根据用户的学习要求生成 2-3 个高质量例句，来展示相关用法。
请确保例句和翻译使用以下JSON格式输出，一个例句翻译对就是一个JSON对象，这一部分必须放在段落最后且无额外内容或注释，以便系统识别：

- 词汇量大致为：{vocab_level}
- 学习目标是：{learning_goal}
- 句子最大难度：{difficulty_level}
- 句子最大长度:{sentence_length_desc}

**重要**: 例句和翻译必须以独立的 JSON 对象格式提供，并置于回答的末尾。不要在 JSON 代码块同一行内添加任何解释性文字或注释，以便系统识别：
系统会自动识别json语法，任何除json语法和代码块符号外的多余的注释，空行，逗号都会被残留，因此请避免任何多余的符合和格式。

```json
{{
  "sentence": "例句原文",
  "translation": "例句翻译"
}}```"""


def build_explanation_prompt(
    sentence: str,
    word_to_explain: str,
    vocab_level: str,
    learning_goal: str,
    difficulty_level: str,
    sentence_length_desc: str,
    include_examples: bool = True,
) -> str:
    """构建 AI 解释的系统提示词。

    include_examples=True（桌面端默认）：含第三步例句生成 + JSON 输出。
    include_examples=False（web 端）：纯解释，不含例句段。
    """
    return EXPLANATION_PROMPT.format(
        sentence=sentence,
        word_to_explain=word_to_explain,
        vocab_level=vocab_level,
        learning_goal=learning_goal,
        difficulty_level=difficulty_level,
        sentence_length_desc=sentence_length_desc,
        examples_length_clause=("除例句外，输出篇幅控制在约200-300字。"
                                if include_examples else "输出篇幅控制在约200-300字。"),
        examples_section=_EXAMPLES_SECTION if include_examples else "",
        examples_tool_clause=("例句生成工具在用户追问时依然可以调用，但仅在用户明确要求更多例句，"
                              "或者你认为提供额外例句能显著帮助用户理解时使用，避免显得刻板和冗余。"
                              if include_examples else ""),
    )


def build_explanation_messages(config, sentence: str, word: str, history: list = None,
                               include_examples: bool = False) -> list:
    """构建 AI 解释对话的 messages：system 留空 + 首条 user 为系统提示词 + 历史追问。

    include_examples：桌面端传 True（含随句例句 JSON），Web 端默认 False。
    qwen3 的 /no_think 后缀由 llm_client 统一处理，这里不关心模型差异。
    """
    system_prompt = build_explanation_prompt(
        sentence=sentence,
        word_to_explain=word,
        vocab_level=config.get("vocab_level", DEFAULT_CONFIG["vocab_level"]),
        learning_goal=config.get("learning_goal", DEFAULT_CONFIG["learning_goal"]),
        difficulty_level=config.get("difficulty_level", DEFAULT_CONFIG["difficulty_level"]),
        sentence_length_desc=config.get("sentence_length_desc", DEFAULT_CONFIG["sentence_length_desc"]),
        # 这里指 AI 解释里的随句例句生成（卡片保存走 /api/card/save_sentence）
        include_examples=include_examples,
    )

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
