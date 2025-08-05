# -*- coding: utf-8 -*-

import re
import html
import aqt
from aqt import mw
from aqt.qt import QAction, QMenu
from anki.hooks import addHook
from .config_manager import get_word_selection_config

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
    
    # 检查功能是否启用
    config = get_word_selection_config()
    if not config.get("enabled", True):
        return
    
    # 获取选中的文本
    try:
        # 通过JavaScript获取选中文本
        selected_text = webview.selectedText()
        if not selected_text:
            return
        
        # 清理选中的文本
        cleaned_text = clean_selected_text(selected_text)
        if not is_valid_word(cleaned_text):
            return
        
        # 存储选中的词汇
        selected_word = cleaned_text
        
        # 添加分隔符（如果菜单不为空）
        if menu.actions():
            menu.addSeparator()
        
        # 创建生成例句的菜单项
        action = QAction(f'为 "{selected_word}" 生成例句', menu)
        action.triggered.connect(lambda: generate_sentences_for_word(selected_word))
        menu.addAction(action)
        
    except Exception as e:
        print(f"ERROR: 处理右键菜单时出错: {e}")

def generate_sentences_for_word(word):
    """
    为选中的词汇生成例句
    """
    try:
        # 检查词汇是否有效
        if not is_valid_word(word):
            aqt.utils.showInfo("选中的文本不是有效的词汇")
            return
        
        # 导入例句生成器（延迟导入避免循环依赖）
        from . import word_sentence_generator
        
        # 调用例句生成器
        word_sentence_generator.show_sentence_generation_dialog(word)
        
    except Exception as e:
        print(f"ERROR: 生成例句时出错: {e}")
        aqt.utils.showInfo(f"生成例句时出错: {str(e)}")

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
