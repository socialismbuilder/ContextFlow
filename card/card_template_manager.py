# -*- coding: utf-8 -*-

import os
import re
from ..config_manager import get_config
from ..tts.tts_manager import _get_anki_lang

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def _load_template(filename: str) -> str:
    path = os.path.join(TEMPLATES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_font_css() -> str:
    config = get_config()
    font_family = config.get("font_family", "默认字体")
    font_bold = config.get("font_bold", True)

    if font_family == "tms论文字体":
        font_css = (
            "font-family: 'Times New Roman', Times, "
            "'Noto Serif SC', 'Source Han Serif', 'SimSun', serif;"
        )
    elif font_family == "考试字体（衬线）":
        font_css = (
            "font-family: Georgia, serif, "
            "'KaiTi', '楷体', 'STKaiti', 'SimKai', 'BiauKai', "
            "'Noto Serif SC', 'Source Han Serif', 'Times New Roman', Times;"
        )
    elif font_family == "网页无衬线字体":
        font_css = (
            "font-family: system-ui, -apple-system, 'Segoe UI', "
            "'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', "
            "Arial, sans-serif;"
        )
    else:
        font_css = ""

    # 加粗作为独立选项，与字体族选择解耦
    if font_bold:
        font_css = (font_css + " font-weight: bold;").strip()

    return " ".join(font_css.split())


def process_highlight(html_text: str) -> str:
    """Convert <u> tags to highlighted spans."""
    return re.compile(r'<u>(.*?)</u>').sub(
        r'<span class="highlight">\1</span> ', html_text
    )


def _fill_template(template: str, sentence: str, translation: str,
                   original_card: str = "", keyword: str = "") -> str:
    """Replace all placeholders in the card template."""

    def strip_html(html_text: str) -> str:
        text = re.sub(r'<[^>]+>', '', html_text)
        return " ".join(text.split())

    def escape_js(text: str) -> str:
        return text.replace("'", "\\'").replace('"', '&quot;')

    def clean_word(kw: str) -> str:
        word = re.sub(r'[（(].*?[）)]', '', kw).strip()
        return word if word else kw

    processed_sentence = process_highlight(sentence)
    processed_translation = process_highlight(translation)
    sentence_text = escape_js(strip_html(processed_sentence))

    # Word button: only show when keyword exists
    if keyword:
        word_text = escape_js(clean_word(keyword))
        word_button = (
            f'<div class="tts-btn" id="tts-word" '
            f'onclick="this.classList.add(\'loading\');'
            f'pycmd(\'contextflow:tts:word:{word_text}\')">'
            f'<span class="tts-label">朗读单词 (Q)</span></div>'
        )
    else:
        word_button = ""

    # Original card area: only show when content exists
    if original_card:
        original_area = (
            '<div class="card-group">'
            '<div class="label" style="color: #777;">原始卡片</div>'
            f'<div class="original-card-text">{original_card}</div>'
            '</div>'
        )
    else:
        original_area = ""

    html = template
    html = html.replace("{FONT_CSS}", get_font_css())
    html = html.replace("{SENTENCE}", processed_sentence)
    html = html.replace("{SENTENCE_TEXT}", sentence_text)
    html = html.replace("{WORD_BUTTON}", word_button)
    html = html.replace("{TRANSLATION}", processed_translation)
    html = html.replace("{ORIGINAL_CARD_AREA}", original_area)
    return html


def _fill_web_template(template: str, sentence: str, translation: str,
                       original_card: str = "", keyword: str = "") -> str:
    """填充 Web 端模板，TTS 按钮使用 JS playTTS() 而非 pycmd。"""

    def strip_html(html_text: str) -> str:
        text = re.sub(r'<[^>]+>', '', html_text)
        return " ".join(text.split())

    def escape_js(text: str) -> str:
        return text.replace("'", "\\'").replace('"', '&quot;')

    def clean_word(kw: str) -> str:
        word = re.sub(r'[（(].*?[）)]', '', kw).strip()
        return word if word else kw

    processed_sentence = process_highlight(sentence)
    processed_translation = process_highlight(translation)
    sentence_text = escape_js(strip_html(processed_sentence))

    if keyword:
        word_text = escape_js(clean_word(keyword))
        word_button = (
            f'<div class="tts-btn" id="tts-word" '
            f'onclick="this.classList.add(\'loading\');playTTS(\'{word_text}\')">'
            f'<span class="tts-label">朗读单词</span></div>'
        )
        # 刷新例句按钮（仅目标牌组，置于按钮组左侧）
        refresh_button = (
            '<div class="tts-btn refresh-btn" id="refresh-btn" '
            'onclick="refreshSentence()" title="重新生成例句">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" '
            'viewBox="0 0 24 24">'
            '<path d="M0 0h24v24H0z" fill="none"/>'
            '<path fill="currentColor" d="M12.077 19q-2.931 0-4.966-2.033q-2.034-2.034-2.034-4.964t2.034-4.966T12.077 5q1.783 0 3.339.847q1.555.847 2.507 2.365V5.5q0-.213.144-.356T18.424 5t.356.144t.143.356v3.923q0 .343-.232.576t-.576.232h-3.923q-.212 0-.356-.144t-.144-.357t.144-.356t.356-.143h3.2q-.78-1.496-2.197-2.364Q13.78 6 12.077 6q-2.5 0-4.25 1.75T6.077 12t1.75 4.25t4.25 1.75q1.787 0 3.271-.968q1.485-.969 2.202-2.573q.085-.196.274-.275q.19-.08.388-.013q.211.067.28.275t-.015.404q-.833 1.885-2.56 3.017T12.077 19"/>'
            '</svg></div>'
        )
    else:
        word_button = ""
        refresh_button = ""

    if original_card:
        original_area = (
            '<div style="margin-top: 10px;">'
            '<div class="label">原始卡片</div>'
            f'<div class="original-card-text">{original_card}</div>'
            '</div>'
        )
    else:
        original_area = ""

    html = template
    html = html.replace("{FONT_CSS}", "")
    html = html.replace("{SENTENCE}", processed_sentence)
    html = html.replace("{SENTENCE_TEXT}", sentence_text)
    html = html.replace("{WORD_BUTTON}", word_button)
    html = html.replace("{REFRESH_BUTTON}", refresh_button)
    html = html.replace("{TRANSLATION}", processed_translation)
    html = html.replace("{ORIGINAL_CARD_AREA}", original_area)
    return html


def get_processed_front_html(sentence: str, keyword: str = "") -> str:
    """Build front HTML: sentence + translation placeholder + TTS buttons."""
    template = _load_template("card.html")
    placeholder = (
        '<div class="translation-placeholder-line"></div>'
        '<div class="translation-placeholder-line"></div>'
    )
    return _fill_template(template, sentence, placeholder, keyword=keyword)


def get_processed_back_html(sentence: str, translation: str,
                            original_html: str, keyword: str = "") -> str:
    """Build back HTML: sentence + translation + original card + TTS buttons."""
    template = _load_template("card.html")
    return _fill_template(template, sentence, translation,
                          original_card=original_html, keyword=keyword)


# ── Web 专用模板 ──────────────────────────────────────

def get_web_front_html(sentence: str, keyword: str = "") -> str:
    """Web 端正面：小字体，TTS 按钮调用 JS API。"""
    template = _load_template("card_web.html")
    placeholder = (
        '<div class="translation-placeholder-line"></div>'
        '<div class="translation-placeholder-line"></div>'
    )
    return _fill_web_template(template, sentence, placeholder, keyword=keyword)


def get_web_back_html(sentence: str, translation: str,
                      original_html: str = "", keyword: str = "") -> str:
    """Web 端背面：小字体，TTS 按钮调用 JS API。"""
    template = _load_template("card_web.html")
    return _fill_web_template(template, sentence, translation,
                              original_card=original_html, keyword=keyword)


def get_card_template_front() -> str:
    """Anki note type front template (used by anki_card_creator.py)."""
    config = get_config()
    language = config.get("learning_language", "英语")
    lang = _get_anki_lang(language)
    font_css = get_font_css()

    return f"""
<style>
.card-group {{
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 8px;
    padding: 15px;
    padding-bottom: 38px;
    margin-bottom: 15px;
    background: rgba(0, 0, 0, 0.03);
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
    text-align: left;
    position: relative;
}}
.night_mode .card-group {{
    border: 1px solid rgba(0, 0, 0, 0.2);
    background: rgba(0, 0, 0, 0.1);
}}
.label {{
    font-size: 14px;
    color: #aaa;
    margin-bottom: 5px;
    text-transform: uppercase;
}}
.night_mode .label {{ color: #777; }}
.card-text {{
    font-size: 36px;
    line-height: 1.3;
    margin-bottom: 10px;
    color: black;
    {font_css}
}}
.night_mode .card-text {{ color: white; }}
.highlight {{
    border-radius: 8px;
    background-color: rgba(255, 150, 150, 0.7);
    padding: 4px 8px;
}}
.translation-placeholder-line {{
    height: 18px;
    width: 80%;
    background: #e0e0e0;
    border-radius: 9px;
    margin: 0 0 8px 0;
}}
.translation-placeholder-line:last-child {{
    width: 55%;
    margin: 0;
}}
.night_mode .translation-placeholder-line {{
    background: rgba(128, 128, 128, 0.7);
}}
.tts-btn-group {{
    position: absolute;
    bottom: 8px;
    right: 10px;
    display: flex;
    gap: 6px;
}}
.tts-btn {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 4px 8px;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.03);
    cursor: pointer;
    font-size: 12px;
    color: #888;
    user-select: none;
}}
.tts-btn:hover {{
    background: rgba(0, 0, 0, 0.07);
    color: #666;
}}
.night_mode .tts-btn {{
    border-color: rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.05);
    color: #777;
}}
.night_mode .tts-btn:hover {{
    background: rgba(255, 255, 255, 0.09);
    color: #aaa;
}}
</style>
<div style="display:none;">{{{{tts {lang}:例句}}}}</div>
<div style="margin: 10px;">
    <div class="card-group">
        <div class="label">例句</div>
        <div class="card-text">{{{{例句}}}}</div>
        <div class="label" style="margin-top: 15px;">翻译</div>
        <div class="card-text" style="line-height: 1.4; opacity: 0.9;">
            <div class="translation-placeholder-line"></div>
            <div class="translation-placeholder-line"></div>
        </div>
        <div class="tts-btn-group">
            <div class="tts-btn" onclick="pycmd('play:q:0')"><span class="tts-label">朗读例句</span></div>
        </div>
    </div>
</div>
"""


def get_card_template_back() -> str:
    """Anki note type back template (used by anki_card_creator.py)."""
    config = get_config()
    language = config.get("learning_language", "英语")
    lang = _get_anki_lang(language)
    font_css = get_font_css()

    return f"""
<style>
.card-group {{
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 8px;
    padding: 15px;
    padding-bottom: 38px;
    margin-bottom: 15px;
    background: rgba(0, 0, 0, 0.03);
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
    text-align: left;
    position: relative;
}}
.night_mode .card-group {{
    border: 1px solid rgba(0, 0, 0, 0.2);
    background: rgba(0, 0, 0, 0.1);
}}
.label {{
    font-size: 14px;
    color: #aaa;
    margin-bottom: 5px;
    text-transform: uppercase;
}}
.night_mode .label {{ color: #777; }}
.card-text {{
    font-size: 36px;
    line-height: 1.3;
    margin-bottom: 10px;
    color: black;
    {font_css}
}}
.night_mode .card-text {{ color: white; }}
.highlight {{
    border-radius: 8px;
    background-color: rgba(255, 150, 150, 0.7);
    padding: 4px 8px;
}}
.original-card-text {{
    font-size: 24px;
    line-height: 1.4;
    opacity: 0.8;
    color: black;
}}
.night_mode .original-card-text {{ color: white; }}
.tts-btn-group {{
    position: absolute;
    bottom: 8px;
    right: 10px;
    display: flex;
    gap: 6px;
}}
.tts-btn {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 4px 8px;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.03);
    cursor: pointer;
    font-size: 12px;
    color: #888;
    user-select: none;
}}
.tts-btn:hover {{
    background: rgba(0, 0, 0, 0.07);
    color: #666;
}}
.night_mode .tts-btn {{
    border-color: rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.05);
    color: #777;
}}
.night_mode .tts-btn:hover {{
    background: rgba(255, 255, 255, 0.09);
    color: #aaa;
}}
</style>
<div style="display:none;">{{{{tts {lang}:例句}}}}</div>
<div style="margin: 10px; position: relative; min-height: 200px;">
    <div class="card-group">
        <div class="label">例句</div>
        <div class="card-text">{{{{例句}}}}</div>
        <div class="label" style="margin-top: 15px;">翻译</div>
        <div class="card-text" style="line-height: 1.4; opacity: 0.9;">{{{{翻译}}}}</div>
        <div class="tts-btn-group">
            <div class="tts-btn" onclick="pycmd('play:a:0')"><span class="tts-label">朗读例句</span></div>
        </div>
    </div>
    <div style="position: absolute; bottom: 10px; right: 10px; font-size: 10px; color: #999;">{{{{来源}}}}</div>
</div>
"""


def update_card_templates() -> bool:
    """Update Anki card templates to reflect current font/TTS settings."""
    try:
        import aqt
        from aqt import mw

        note_type_name = "ContextFlow例句翻译"
        existing_models = mw.col.models.all()

        for model in existing_models:
            if model['name'] == note_type_name:
                template = model['tmpls'][0]
                template['qfmt'] = get_card_template_front()
                template['afmt'] = get_card_template_back()

                mw.col.models.save(model)
                mw.col.save()

                print("SUCCESS: 已更新卡片模板以反映字体设置")
                return True

        print(f"WARNING: 未找到笔记类型 '{note_type_name}'，无法更新模板")
        return False

    except Exception as e:
        print(f"ERROR: 更新卡片模板失败: {e}")
        return False
