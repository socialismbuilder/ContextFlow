import aqt
from aqt import mw
from aqt import gui_hooks
import time
import re
from anki.cards import Card
from PyQt6.QtCore import QTimer
from . import config_manager
from .config_manager import get_config, clean_html
from .cache_manager import load_cache, pop_cache
from .card_template_manager import get_processed_back_html, get_processed_front_html
from .stats import add_stats
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


def _update_showing_state(sentence, translation):
    """同步更新所有存储当前显示句子的位置"""
    global showing_sentence, showing_translation
    showing_sentence = sentence
    showing_translation = translation
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
        _update_showing_state(sentence, translation)
        html_result = get_processed_front_html(sentence)

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
    """处理缓存未命中：加入队列，启动进度条轮询等待。返回 HTML"""
    print(f"DEBUG: 缓存未命中 '{keyword}'。加入队列并开始等待。")
    _task_manager.reorganize_queue(keyword)

    max_wait = 30
    start_time = time.time()
    timer = QTimer()
    timer.setParent(mw)

    # 进度条上只显示单词，去掉括号中的翻译避免剧透
    display_keyword = re.sub(r'[（(].*?[）)]', '', keyword).strip()

    mw.progress.start(
        immediate=True,
        label=f"正在为 '{display_keyword}' 生成例句...",
        min=0,
        max=max_wait
    )

    def _finish_progress():
        """统一清理进度条和 timer"""
        timer.stop()
        mw.progress.finish()

    def update_ui():
        # 用户点击了进度条的关闭按钮
        if mw.progress.want_cancel():
            _finish_progress()
            return

        elapsed = int(time.time() - start_time)

        mw.progress.update(
            label=f"正在为 '{display_keyword}' 生成例句... (已等待{elapsed}秒/{max_wait}秒)",
            value=elapsed,
            max=max_wait
        )

        if elapsed >= max_wait:
            _finish_progress()
            return

        if load_cache(keyword):
            _finish_progress()
            mw.reset()

    timer.timeout.connect(update_ui)
    timer.start(100)

    _update_showing_state("例句生成中...", "")
    return get_processed_front_html("例句生成中...")


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

    state = aqt.mw.reviewer.state if aqt.mw.reviewer else 'unknown'

    if state == 'question':
        result = _render_question_side(card, base_deck_name, field_index_match)
        return result if result is not None else html

    if state == 'answer':
        return get_processed_back_html(showing_sentence, showing_translation, html)

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


def register_hooks():
    """注册所有需要的钩子，并延迟启动工作线程"""
    gui_hooks.card_will_show.append(on_card_render)
    gui_hooks.profile_will_close.append(stop_worker)
    gui_hooks.stats_dialog_will_show.append(add_stats)

    try:
        from . import context_menu
        context_menu.register_context_menu()
        print("DEBUG: 选中词汇例句生成功能已启用")
    except Exception as e:
        print(f"ERROR: 注册选中词汇例句生成功能失败: {e}")

    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1000, start_worker)
