# -*- coding: utf-8 -*-

import re
from .config_manager import get_config

def get_font_css():
    """
    根据配置获取字体CSS样式
    """
    config = get_config()
    font_family = config.get("font_family", "默认字体")
    
    if font_family == "tms论文字体":
        font_css = """
            font-family: 'Times New Roman', Times, 
                         'Noto Serif SC', /* 思源宋体-中文 */
                         'Source Han Serif', /* 源样明体-中日韩 */
                         'SimSun', /* 宋体-中文 */
                         serif;
        """
    elif font_family == "考试字体（衬线）":
        font_css = """
            font-family: Georgia, serif,
                         'KaiTi', '楷体', 'STKaiti', /* 楷体-中文 */
                         'SimKai', /* 华文楷体 */
                         'BiauKai', /* 标楷体-繁体 */
                         'Noto Serif SC', /* 思源宋体-中文备用 */
                         'Source Han Serif', /* 源样明体-中日韩 */
                         'Times New Roman', Times;
        """
    else:
        font_css = ""  # 默认字体使用系统默认
    
    # 清理CSS格式（移除多余空格和换行）
    return ' '.join(font_css.split())

def get_base_css():
    """
    获取基础CSS样式（不包含字体）
    """
    return """
        .card-group {
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(0, 0, 0, 0.03);
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            text-align: left;
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
            FONT_CSS_PLACEHOLDER
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
        .original-card-text {
            font-size: 24px;
            line-height: 1.4;
            opacity: 0.8;
            color: black;
        }
        .night_mode .original-card-text {
            color: white;
        }
    """

def get_card_template_front():
    """
    获取卡片正面模板
    """
    font_css = get_font_css()
    base_css = get_base_css().replace("FONT_CSS_PLACEHOLDER", font_css)
    
    return """
<style>
""" + base_css + """
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
"""

def get_card_template_back():
    """
    获取卡片背面模板
    """
    font_css = get_font_css()
    base_css = get_base_css().replace("FONT_CSS_PLACEHOLDER", font_css)
    
    return """
<style>
""" + base_css + """
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
"""

def process_highlight(html_text):
    """
    处理文本中的高亮标记，将<u>标签转换为高亮span
    """
    pattern = re.compile(r'<u>(.*?)</u>')
    return pattern.sub(r'<span class="highlight">\1</span> ', html_text)

def get_processed_front_html(sentence):
    """
    获取处理后的正面HTML，用于main_logic.py
    """
    font_css = get_font_css()
    processed_sentence = process_highlight(sentence)
    base_css = get_base_css().replace("FONT_CSS_PLACEHOLDER", font_css)
    
    return f"""
<style>
{base_css}
</style>
<div style="margin: 10px;">
    <div class="card-group">
        <div class="label">例句</div>
        <div class="card-text">{processed_sentence}</div>

        <div class="label" style="margin-top: 15px;">翻译</div>
        <div class="card-text" style="line-height: 1.4; opacity: 0.9;">
            <div class="translation-placeholder-line"></div>
            <div class="translation-placeholder-line"></div>
        </div>
    </div>
</div>
"""

def get_processed_back_html(sentence, translation, original_html):
    """
    获取处理后的背面HTML，用于main_logic.py
    """
    font_css = get_font_css()
    processed_sentence = process_highlight(sentence)
    processed_translation = process_highlight(translation)
    base_css = get_base_css().replace("FONT_CSS_PLACEHOLDER", font_css)
    
    return f"""
<style>
{base_css}
</style>
<div style="margin: 10px;">
    <div class="card-group">
        <div class="label">例句</div>
        <div class="card-text">{processed_sentence}</div>

        <div class="label" style="margin-top: 15px;">翻译</div>
        <div class="card-text" style="line-height: 1.4; opacity: 0.9;">{processed_translation}</div>
    </div>

    <div class="card-group">
        <div class="label" style="color: #777;">原始卡片</div>
        <div class="original-card-text">{original_html}</div>
    </div>
</div>
"""

def update_card_templates():
    """
    更新Anki中的卡片模板，以反映当前的字体设置
    """
    try:
        import aqt
        from aqt import mw
        
        # 获取笔记类型
        note_type_name = "ContextFlow例句翻译"
        existing_models = mw.col.models.all()
        
        for model in existing_models:
            if model['name'] == note_type_name:
                # 更新模板
                template = model['tmpls'][0]  # 获取第一个模板
                template['qfmt'] = get_card_template_front()
                template['afmt'] = get_card_template_back()
                
                # 保存模型
                mw.col.models.save(model)
                mw.col.save()
                
                print(f"SUCCESS: 已更新卡片模板以反映字体设置")
                return True
        
        print(f"WARNING: 未找到笔记类型 '{note_type_name}'，无法更新模板")
        return False
        
    except Exception as e:
        print(f"ERROR: 更新卡片模板失败: {e}")
        return False