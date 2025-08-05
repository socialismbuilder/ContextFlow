# -*- coding: utf-8 -*-

import aqt
from aqt import mw
from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QScrollArea, QWidget, QFrame, QMessageBox
from .config_manager import get_config, get_word_selection_config
from .api_client import get_api_response, get_message_content, parse_message_content_to_sentence_pairs
from . import main_logic
import time

def create_word_prompt(word, config):
    """
    为选中词汇创建专门的提示词
    """
    word_config = get_word_selection_config()
    
    # 检查是否使用自定义提示词
    if word_config.get("use_custom_prompt", False) and word_config.get("custom_prompt"):
        base_prompt = word_config["custom_prompt"]
    else:
        # 使用默认的简化提示词
        base_prompt = '''你是一个学习插件的例句生成助手
请为{language}学习者生成{sentence_count}个包含关键词 '{word}' 的{language}例句，并附带中文翻译。

学习者信息：
- 当前词汇量大致为：{vocab_level}
- 学习目标是：{learning_goal}
- 句子最大难度：{difficulty_level}
- 句子最大长度:{sentence_length_desc}

例句生成规则：
- 提供的关键词 '{word}' 是一个完整的词汇/短语
- 每个例句必须包含关键词 '{word}'
- {sentence_count}个例句应尽量全面的覆盖关键词的各种用法和含义
- 例句和翻译必须分别是单一语言，不得双语混杂

输出格式要求：
- 必须返回严格的JSON格式，结构为：{{"sentences": [[{language}例句1, 中文翻译1], [{language}例句2, 中文翻译2], ..., [{language}例句{sentence_count}, 中文翻译{sentence_count}]]}}
- 每个子数组必须包含两个字符串元素：第一个是包含关键词'{word}'的{language}例句，第二个是对应的中文翻译
- **绝对不要** 输出任何其他内容，如序号、标题、解释或额外字段
- 必须以`sentences`命名变量，而不是{word}

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

示例仅为格式参考。语言，难度，句子长度等信息请按照生成规则。请严格按照上述要求生成。'''
    
    # 格式化提示词
    formatted_prompt = base_prompt.format(
        word=word,
        language=config.get("learning_language", "英语"),
        vocab_level=config.get("vocab_level", "大学英语四级 CET-4 (4000词)"),
        learning_goal=config.get("learning_goal", "提升日常浏览英文网页与资料的流畅度"),
        difficulty_level=word_config.get("difficulty_level", "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围"),
        sentence_length_desc=word_config.get("sentence_length", "中等长度句 (约25-40词): 通用对话及文章常用长度"),
        sentence_count=word_config.get("sentence_count", 3)
    )
    
    return formatted_prompt

def generate_sentences_for_word(word):
    """
    为选中词汇生成例句
    """
    try:
        config = get_config()
        word_config = get_word_selection_config()
        
        # 创建提示词
        prompt = create_word_prompt(word, config)
        
        # 调用API生成例句
        response = get_api_response(config, prompt)
        if not response:
            return None
        
        # 解析响应
        message_content = get_message_content(response, word)
        if not message_content:
            return None
        
        # 解析例句对
        sentence_pairs = parse_message_content_to_sentence_pairs(message_content, word)
        return sentence_pairs
        
    except Exception as e:
        print(f"ERROR: 为词汇 '{word}' 生成例句时出错: {e}")
        return None

def show_sentence_generation_dialog(word):
    """
    显示例句生成对话框
    """
    try:
        # 导入对话框模块（延迟导入避免循环依赖）
        from . import sentence_dialog
        
        # 显示对话框
        dialog = sentence_dialog.SentenceManagementDialog(word, mw)
        dialog.exec()
        
    except Exception as e:
        print(f"ERROR: 显示例句生成对话框时出错: {e}")
        aqt.utils.showInfo(f"显示例句生成对话框时出错: {str(e)}")
