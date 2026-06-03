import aqt
from aqt import mw
from aqt import gui_hooks
import re
import threading
from anki.cards import Card
from PyQt6.QtCore import QTimer
from . import config_manager
from .config_manager import get_config, clean_html
from .cache.cache_manager import load_cache, pop_cache
from .card.card_template_manager import get_processed_back_html, get_processed_front_html
from .tts.tts_manager import tts_manager
from .ui.stats import add_stats
from .task_manager import SentenceTaskManager

# --- 单例实例 ---
_task_manager = SentenceTaskManager()

# --- 向后兼容的模块级属性 ---
executor = None
max_workers = 0
task_queue = _task_manager.task_queue
processing_keywords = _task_manager.processing_keywords
cache_lock = _task_manager.cache_lock
stop_event = _task_manager.stop_event
showing_sentence = ""
showing_translation = ""
showing_keyword = ""
WAITING_SENTENCE_TEXT = "例句生成中..."


def _update_showing_state(sentence, translation, keyword=""):
    """同步更新所有存储当前显示句子的位置"""
    global showing_sentence, showing_translation, showing_keyword
    showing_sentence = sentence
    showing_translation = translation
    showing_keyword = keyword
    _task_manager.showing_sentence = sentence
    _task_manager.showing_translation = translation
    config_manager.showing_sentence = sentence
    config_manager.showing_translation = translation


def _extract_keyword(card, field_index_match):
    """从卡片中提取关键词，失败返回 None"""
    try:
        note = card.note()
        field_index = int(field_index_match.group(1)) - 1 if field_index_match else 0
        if field_index < 0 or (note.fields and field_index >= len(note.fields)):
            field_index = 0
        keyword = note.fields[field_index].strip() if note.fields and len(note.fields) > field_index else ""
        keyword = clean_html(keyword)
        return keyword if keyword else None
    except Exception as e:
        aqt.utils.showInfo(f"获取卡片字段失败：{str(e)}")
        return None


def _handle_cache_hit(keyword, popped_pair):
    """处理缓存命中：更新显示状态，若缓存耗尽则重新入队。返回 HTML"""
    try:
        sentence, translation = popped_pair
        _update_showing_state(sentence, translation, keyword)
        html_result = get_processed_front_html(sentence, keyword)

        if not load_cache(keyword):
            print(f"DEBUG: 关键词 '{keyword}' 缓存已用尽，以最低优先级重新加入队列。")
            _task_manager.reorganize_queue(keyword, is_repopulate=True)

        return html_result
    except Exception as e:
        error_type = type(e).__name__
        error_msg = f"处理缓存时发生意外错误 ({error_type})：{str(e)}"
        print(error_msg)
        aqt.utils.showInfo(error_msg)
        _update_showing_state("缓存处理错误", "")
        return get_processed_front_html("缓存处理错误")


def _handle_cache_miss(keyword):
    """处理缓存未命中：加入队列并返回占位内容。"""
    print(f"DEBUG: 缓存未命中 '{keyword}'。加入队列并开始等待。")
    _task_manager.reorganize_queue(keyword)
    display_keyword = re.sub(r'[（(].*?[）)]', '', keyword).strip()
    aqt.utils.tooltip(f"正在为 '{display_keyword}' 生成例句...", period=1500, parent=mw)

    _update_showing_state(WAITING_SENTENCE_TEXT, "", keyword)
    return get_processed_front_html(WAITING_SENTENCE_TEXT)


def _refresh_waiting_card_if_ready(keyword: str):
    """When the current question card is still waiting for this keyword, rerender it."""
    try:
        reviewer = aqt.mw.reviewer
        if reviewer is None or reviewer.state != 'question':
            return

        if keyword != showing_keyword or showing_sentence != WAITING_SENTENCE_TEXT:
            return

        if not load_cache(keyword):
            return

        QTimer.singleShot(0, mw.reset)
    except Exception as e:
        print(f"ERROR: Failed to refresh waiting card for '{keyword}': {e}")


def _render_question_side(card, base_deck_name, field_index_match):
    """渲染问题面：尝试缓存命中，否则等待生成。返回 HTML"""
    keyword = _extract_keyword(card, field_index_match)
    if not keyword:
        return None  # 无关键词，由调用方返回原始 html

    popped_pair = pop_cache(keyword)
    if popped_pair:
        html_result = _handle_cache_hit(keyword, popped_pair)
    else:
        html_result = _handle_cache_miss(keyword)

    # 预加载后续卡片
    try:
        upcoming_keywords = _task_manager.get_upcoming_card_keywords(base_deck_name)
        _task_manager.reorganize_queue(upcoming_keywords)
    except Exception as e:
        print(f"ERROR: Failed to preload and reorganize task queue: {e}")

    return html_result


def _is_target_deck(card, current_deck, base_deck_name):
    """判断卡片是否属于目标牌组且为正面（ord==0）"""
    return (current_deck == base_deck_name or current_deck.startswith(base_deck_name + "::")) and card.ord == 0


def _strip_native_audio(html: str) -> str:
    """Remove [sound:xxx] tags from HTML to prevent native audio playback."""
    return re.sub(r'\[sound:[^\]]*\]', '', html)


def _auto_play_tts():
    """Auto-click the word TTS button after card renders."""
    try:
        from aqt import mw
        if mw and mw.reviewer and mw.reviewer.web:
            mw.reviewer.web.eval(
                "var btn=document.getElementById('tts-word');"
                "if(btn)btn.click();"
            )
    except Exception:
        pass


def on_card_render(html: str, card: Card, context: str) -> str:
    """卡片渲染钩子，处理问题面和答案面的显示逻辑"""
    config = get_config()
    try:
        current_deck = aqt.mw.col.decks.name(card.did)
    except Exception as e:
        print(f"ERROR: 获取牌组名称失败 for card {card.id}: {e}")
        return html

    config_deck_name = config.get("deck_name")
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name

    if not _is_target_deck(card, current_deck, base_deck_name):
        return html

    replace_audio = config.get("tts_replace_audio", False)
    state = aqt.mw.reviewer.state if aqt.mw.reviewer else 'unknown'

    if state == 'question':
        result = _render_question_side(card, base_deck_name, field_index_match)
        if result is not None:
            if replace_audio:
                QTimer.singleShot(0, _auto_play_tts)
            return result
        if replace_audio:
            #return _strip_native_audio(html)
            pass
        return html

    if state == 'answer':
        result = get_processed_back_html(showing_sentence, showing_translation, html, showing_keyword)
        if replace_audio:
            #result = _strip_native_audio(result)
            pass
            QTimer.singleShot(0, _auto_play_tts)
        return result

    return html


def start_worker():
    """启动后台例句生成工作线程"""
    global executor, max_workers
    _task_manager.start(get_config())
    executor = _task_manager.executor
    max_workers = _task_manager.max_workers


def stop_worker():
    """停止后台例句生成工作线程"""
    global executor, max_workers
    _task_manager.stop()
    executor = None
    max_workers = 0


def _stop_tts_loading():
    """Remove loading state from all TTS buttons in the reviewer."""
    try:
        from aqt import mw
        if mw and mw.reviewer and mw.reviewer.web:
            mw.reviewer.web.eval(
                "document.querySelectorAll('.tts-btn.loading').forEach(function(el){el.classList.remove('loading')})"
            )
    except Exception:
        pass


def _handle_js_message(handled, message, context):
    """Handle pycmd messages from card HTML via webview_did_receive_js_message."""
    if not message.startswith("contextflow:"):
        return handled

    parts = message.split(":", 2)
    if len(parts) < 3:
        return handled

    command = parts[1]
    payload = parts[2]

    if command == "tts":
        if payload.startswith("sentence:"):
            text = payload[len("sentence:"):]
        elif payload.startswith("word:"):
            text = payload[len("word:"):]
        else:
            text = payload

        if text:
            cached = tts_manager.play_cached(text)
            if cached:
                _stop_tts_loading()
            elif tts_manager.uses_direct_playback():
                try:
                    tts_manager.play_direct(text)
                except Exception as e:
                    print(f"ERROR: TTS direct playback failed: {e}")
                _stop_tts_loading()
            else:
                def _tts_background():
                    try:
                        result = tts_manager.generate(text)
                    except Exception as e:
                        print(f"ERROR: TTS generation failed: {e}")
                        result = None

                    def _on_tts_done():
                        _stop_tts_loading()
                        if result:
                            audio_data, ext = result
                            try:
                                from .tts.tts_manager import _play_bytes
                                _play_bytes(audio_data, ext)
                            except Exception as e:
                                print(f"ERROR: TTS play file failed: {e}")

                    mw.taskman.run_on_main(_on_tts_done)

                threading.Thread(target=_tts_background, daemon=True).start()
        return (True, None)

    return handled


def _block_native_audio(card, tags):
    """Block native card audio autoplay when tts_replace_audio is enabled.

    tags and card.question_av_tags() share the same cached list object,
    so we cannot mutate tags without breaking manual replay. Instead,
    save original contents, clear, and schedule restore after play_tags
    has already been called with the empty list.
    """
    if not get_config().get("tts_replace_audio", False):
        return

    original = tags[:]
    tags.clear()
    # Restore after the current event loop cycle so reviewer's
    # play_tags(sounds) sees an empty list, but card.question_av_tags()
    # still returns the full list for future manual clicks.
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, lambda: tags.extend(original))


def register_hooks():
    """注册所有需要的钩子，并延迟启动工作线程"""
    _task_manager.on_keyword_ready = _refresh_waiting_card_if_ready
    gui_hooks.card_will_show.append(on_card_render)
    gui_hooks.webview_did_receive_js_message.append(_handle_js_message)
    gui_hooks.reviewer_will_play_question_sounds.append(_block_native_audio)
    gui_hooks.reviewer_will_play_answer_sounds.append(_block_native_audio)

    gui_hooks.profile_will_close.append(stop_worker)
    gui_hooks.stats_dialog_will_show.append(add_stats)

    try:
        from .ui import context_menu
        context_menu.register_context_menu()
        print("DEBUG: 选中词汇例句生成功能已启用")
    except Exception as e:
        print(f"ERROR: 注册选中词汇例句生成功能失败: {e}")

    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1000, start_worker)
