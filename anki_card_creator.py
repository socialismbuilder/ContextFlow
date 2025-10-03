# -*- coding: utf-8 -*-

import aqt
from aqt import mw
from anki.notes import Note
import time
from .card_template_manager import get_card_template_front, get_card_template_back

def get_or_create_deck(deck_name):
    """
    获取或创建指定名称的牌组
    """
    try:
        # 获取牌组ID，如果不存在则创建
        deck_id = mw.col.decks.id(deck_name)
        return deck_id
    except Exception as e:
        print(f"ERROR: 获取或创建牌组 '{deck_name}' 失败: {e}")
        return None

def get_or_create_note_type():
    """
    获取或创建用于例句翻译的笔记类型
    """
    try:
        note_type_name = "ContextFlow例句翻译"
        
        # 检查是否已存在该笔记类型
        existing_models = mw.col.models.all()
        for model in existing_models:
            if model['name'] == note_type_name:
                return model
        
        # 创建新的笔记类型
        model = mw.col.models.new(note_type_name)
        
        # 添加字段
        fields = [
            {"name": "例句", "description": "目标例句"},
            {"name": "翻译", "description": "例句的中文翻译"},
            {"name": "来源", "description": "例句来源标记"}
        ]
        
        for field_info in fields:
            field = mw.col.models.new_field(field_info["name"])
            mw.col.models.add_field(model, field)
        
        # 添加卡片模板
        template = mw.col.models.new_template("例句翻译卡片")
        template['qfmt'] = get_card_template_front()
        template['afmt'] = get_card_template_back()
        
        mw.col.models.add_template(model, template)
        mw.col.models.add(model)
        mw.col.models.save(model)
        
        return model
        
    except Exception as e:
        print(f"ERROR: 创建笔记类型失败: {e}")
        return None

def create_sentence_card(sentence, translation, deck_name):
    """
    创建例句翻译卡片
    """
    try:
        # 获取或创建牌组
        deck_id = get_or_create_deck(deck_name)
        if not deck_id:
            print(f"ERROR: 无法获取或创建牌组 '{deck_name}'")
            return False
        
        # 获取或创建笔记类型
        note_type = get_or_create_note_type()
        if not note_type:
            print("ERROR: 无法获取或创建笔记类型")
            return False
        
        # 创建笔记
        note = Note(mw.col, note_type)
        
        # 设置字段值
        note.fields[0] = sentence  # 例句
        note.fields[1] = translation  # 翻译
        note.fields[2] = f"ContextFlow自动生成 - {time.strftime('%Y-%m-%d %H:%M')}"  # 来源
        
        # 设置牌组
        note.note_type()['did'] = deck_id
        
        # 添加笔记到集合
        mw.col.add_note(note, deck_id)
        
        # 保存更改
        mw.col.save()
        
        print(f"SUCCESS: 成功创建例句翻译卡片 - 例句: {sentence}, 牌组: {deck_name}")
        return True
        
    except Exception as e:
        print(f"ERROR: 创建例句翻译卡片失败: {e}")
        return False

def check_deck_exists(deck_name):
    """
    检查指定牌组是否存在
    """
    try:
        deck_names = [deck['name'] for deck in mw.col.decks.all()]
        return deck_name in deck_names
    except Exception as e:
        print(f"ERROR: 检查牌组是否存在时出错: {e}")
        return False

def get_available_decks():
    """
    获取所有可用的牌组名称
    """
    try:
        decks = mw.col.decks.all()
        deck_names = [deck['name'] for deck in decks]
        return sorted(deck_names)
    except Exception as e:
        print(f"ERROR: 获取可用牌组列表时出错: {e}")
        return []

def validate_card_data(sentence, translation):
    """
    验证卡片数据的有效性
    """
    if not sentence or not sentence.strip():
        return False, "例句不能为空"
    
    if not translation or not translation.strip():
        return False, "翻译不能为空"
    
    return True, "数据有效"
