# -*- coding: utf-8 -*-

import aqt
from aqt import mw
from anki.notes import Note
import time

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
        template['qfmt'] = '''
<style>
    .card-group {
        border: 1px solid rgba(0, 0, 0, 0.1);
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        background: rgba(0, 0, 0, 0.03);
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        text-align: left; /* 新增：设置文本左对齐 */
    }
    .night_mode .card-group {
        border: 1px solid rgba(0, 0, 0, 0.2);
        background: rgba(0, 0, 0, 0.1);
    }
    .label {
        font-size: 14px;
        color: #aaa;
        margin-bottom: 5px;
        text-transform: uppercase;
    }
    .night_mode .label {
        color: #777;
    }
    .card-text {
        font-size: 36px;
        font-weight: bold;
        line-height: 1.3;
        margin-bottom: 10px;
        color: black;
    }
    .night_mode .card-text {
        color: white;
    }
    .highlight {
        border-radius:8px; 
        background-color:rgba(255, 150, 150, 0.7); 
        padding:4px 8px;
    }
    .translation-placeholder-line {
        height:18px; 
        width:80%;
        background:#e0e0e0;
        border-radius:9px; 
        margin:0 0 8px 0;
    }
    .translation-placeholder-line:last-child {
        width:55%;
        margin:0 0 0 0;
    }
    .night_mode .translation-placeholder-line {
        background: rgba(128, 128, 128, 0.7);
    }
</style>
<div style="margin: 10px;">
    <div class="card-group">
        <div class="label">例句</div>
        <div class="card-text">{{例句}}</div>

        <div class="label" style="margin-top: 15px;">翻译</div>
        <div class="card-text" style="line-height: 1.4; opacity: 0.9;">
            <div class="translation-placeholder-line"></div>
            <div class="translation-placeholder-line"></div>
        </div>
    </div>
</div>
'''
        template['afmt'] = '''
<style>
    .card-group {
        border: 1px solid rgba(0, 0, 0, 0.1);
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        background: rgba(0, 0, 0, 0.03);
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        text-align: left; /* 新增：设置文本左对齐 */
    }
    .night_mode .card-group {
        border: 1px solid rgba(0, 0, 0, 0.2);
        background: rgba(0, 0, 0, 0.1);
    }
    .label {
        font-size: 14px;
        color: #aaa;
        margin-bottom: 5px;
        text-transform: uppercase;
    }
    .night_mode .label {
        color: #777;
    }
    .card-text {
        font-size: 36px;
        font-weight: bold;
        line-height: 1.3;
        margin-bottom: 10px;
        color: black;
    }
    .night_mode .card-text {
        color: white;
    }
    .highlight {
        border-radius:8px; 
        background-color:rgba(255, 150, 150, 0.7); 
        padding:4px 8px;
    }
    .original-card-text {
        font-size: 24px;
        line-height: 1.4;
        opacity: 0.8;
        color: black;
    }
    .night_mode .original-card-text {
        color: white;
    }
</style>
<div style="margin: 10px; position: relative; min-height: 200px;">
    <div class="card-group">
        <div class="label">例句</div>
        <div class="card-text">{{例句}}</div>

        <div class="label" style="margin-top: 15px;">翻译</div>
        <div class="card-text" style="line-height: 1.4; opacity: 0.9;">{{翻译}}</div>
    </div>

    <div style="position: absolute; bottom: 10px; right: 10px; font-size: 10px; color: #999;">{{来源}}</div>
</div>
'''
        
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
