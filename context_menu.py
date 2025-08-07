# -*- coding: utf-8 -*-

import re
import html
import aqt
from aqt import mw
from aqt.qt import QAction, QMenu
from anki.hooks import addHook
from .config_manager import get_config

# 全局变量存储选中的词汇
selected_word = ""

def clean_selected_text(text):
    """
    清理选中的文本，移除HTML标签和特殊字符
    """
    if not text:
        return ""
    
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 解码HTML实体
    text = html.unescape(text)
    # 移除多余的空白字符
    text = re.sub(r'\s+', ' ', text).strip()
    # 只保留字母、数字和基本标点
    text = re.sub(r'[^\w\s\'-]', '', text)
    
    return text

def is_valid_word(word):
    """
    检查是否是有效的单词
    """
    if not word or len(word) < 2:
        return False
    
    # 检查是否包含字母
    if not re.search(r'[a-zA-Z]', word):
        return False
    
    # 检查长度是否合理（1-50个字符）
    if len(word) > 50:
        return False
    
    return True

def on_webview_context_menu(webview, menu):
    """
    处理网页视图的右键菜单事件
    """
    global selected_word
    current_deck = mw.col.decks.name(mw.reviewer.card.did)
    config = get_config()
    config_deck_name = config.get("deck_name")
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name
    if (current_deck == base_deck_name or current_deck.startswith(base_deck_name + "::")):
        # 获取选中的文本
        try:
            # 通过JavaScript获取选中文本
            selected_text = webview.selectedText()
            
            # 清理选中的文本
            cleaned_text = clean_selected_text(selected_text)
            
            # 存储选中的词汇
            selected_word = cleaned_text
            
            # 添加分隔符（如果菜单不为空）
            if menu.actions():
                menu.addSeparator()
            
            from . import main_logic

            # 添加新的菜单项
            # 1. 刷新例句
            refresh_action = QAction(f'刷新例句', menu)
            refresh_action.triggered.connect(lambda: refresh_example_sentences(selected_word))
            menu.addAction(refresh_action)
            
            # 2. 存储例句
            store_action = QAction(f'存储例句', menu)
            store_action.triggered.connect(lambda: store_example_sentences(selected_word))
            menu.addAction(store_action)
            
            # 3. AI详细解释
            if selected_word:
                explain_action = QAction(f'AI详细解释 "{selected_word}"', menu)
                explain_action.triggered.connect(lambda: explain_word_with_ai(main_logic.showing_sentence, selected_word))
                menu.addAction(explain_action)
            
            
        except Exception as e:
            print(f"ERROR: 处理右键菜单时出错: {e}")

# 新增的函数
def refresh_example_sentences(word):
    """
    刷新例句
    """
    mw.reset()
    # 在这里实现详细的刷新例句逻辑

def store_example_sentences(word):
    """
    存储例句
    """
    print(f"测试：存储例句 for {word}")
    # 在这里实现详细的存储例句逻辑

from .ai_explanation_dialog import AIExplanationDialog # 导入AIExplanationDialog

def explain_word_with_ai(sentence, word):
    """
    用AI详细解释词汇
    """
    dialog = AIExplanationDialog(mw.app.activeWindow(), sentence, word)
    dialog.exec()

def register_context_menu():
    """
    注册右键菜单钩子
    """
    try:
        # 注册网页视图右键菜单钩子
        from aqt import gui_hooks
        gui_hooks.webview_will_show_context_menu.append(on_webview_context_menu)
        print("DEBUG: 右键菜单钩子注册成功")
    except Exception as e:
        print(f"ERROR: 注册右键菜单钩子失败: {e}")

def unregister_context_menu():
    """
    取消注册右键菜单钩子
    """
    try:
        from aqt import gui_hooks
        if on_webview_context_menu in gui_hooks.webview_will_show_context_menu:
            gui_hooks.webview_will_show_context_menu.remove(on_webview_context_menu)
        print("DEBUG: 右键菜单钩子取消注册成功")
    except Exception as e:
        print(f"ERROR: 取消注册右键菜单钩子失败: {e}")
