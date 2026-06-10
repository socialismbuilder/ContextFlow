# -*- coding: utf-8 -*-
"""
Web 端卡片操作封装 —— 线程安全的卡片获取、渲染、答题逻辑。
所有 mw.col 操作必须在 Qt 主线程执行，由调用方通过 run_on_main_async() 异步桥接。
"""

import re
import os
import time

# ── Web 端计时器 ──────────────────────────────────────────────
# 记录每张卡片在 Web 端首次展示的时间戳，用于计算真实学习时间。
# 桌面端由 reviewer 在 getCard() 时自动 start_timer()，
# Web 端需要在获取卡片时手动记录，答题时传递给 answerCard()。
_card_show_times: dict[int, float] = {}  # card_id -> time.time() 时间戳


# ── 媒体 URL 重写 ──────────────────────────────────────────────

def rewrite_media_urls(html: str) -> str:
    """将卡片 HTML 中的相对媒体路径重写为 /media/ API 端点。"""
    # <img src="foo.jpg"> → <img src="/media/foo.jpg">
    html = re.sub(
        r'(src=["\'])(?!https?://|/)([^"\']+)(["\'])',
        r'\1/media/\2\3',
        html,
    )
    # [sound:foo.mp3] → <audio controls src="/media/foo.mp3"></audio>
    html = re.sub(
        r'\[sound:([^\]]+)\]',
        r'<audio controls src="/media/\1" preload="auto"></audio>',
        html,
    ) 
    # 移除 pycmd() 调用（Anki 内部 JS bridge，Web 端不可用）
    html = re.sub(r'pycmd\([^)]*\)', '', html)
    # 移除 [anki:play:...] 标签
    html = re.sub(r'\[anki:play:[^\]]*\]', '', html)
    return html


# ── ContextFlow 例句渲染 ──────────────────────────────────────

def _is_target_deck(card, current_deck, base_deck_name):
    """判断卡片是否属于目标牌组且为正面（ord==0）"""
    return (current_deck == base_deck_name or current_deck.startswith(base_deck_name + "::")) and card.ord == 0


def _extract_keyword(card, field_index_match):
    """从卡片中提取关键词（复用 main_logic 的逻辑）"""
    try:
        from .config_manager import clean_html
        note = card.note()
        field_index = int(field_index_match.group(1)) - 1 if field_index_match else 0
        if field_index < 0 or (note.fields and field_index >= len(note.fields)):
            field_index = 0
        keyword = note.fields[field_index].strip() if note.fields and len(note.fields) > field_index else ""
        keyword = clean_html(keyword)
        return keyword if keyword else None
    except Exception:
        return None


def _render_web_question(card, original_html):
    """
    Web 端问题面渲染：注入 ContextFlow 例句。
    不依赖 reviewer.state、QTimer、进度条。
    返回修改后的 HTML，如果非目标牌组则返回原始 HTML。
    """
    from .config_manager import get_config
    from .cache.cache_manager import pop_cache, load_cache
    from .card.card_template_manager import get_web_front_html
    from . import main_logic

    config = get_config()
    try:
        from aqt import mw
        current_deck = mw.col.decks.name(card.did)
    except Exception:
        return original_html

    config_deck_name = config.get("deck_name")
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name

    if not _is_target_deck(card, current_deck, base_deck_name):
        return original_html

    keyword = _extract_keyword(card, field_index_match)
    if not keyword:
        return original_html

    # 查缓存
    popped_pair = pop_cache(keyword)
    if popped_pair:
        sentence, translation = popped_pair
        # 更新全局显示状态（复用 main_logic 的状态管理）
        main_logic._update_showing_state(sentence, translation, keyword)
        # 如果缓存用尽，重新入队
        if not load_cache(keyword):
            main_logic._task_manager.reorganize_queue(keyword, is_repopulate=True)
        # 生成例句 HTML
        sentence_html = get_web_front_html(sentence, keyword)

        # 预取后续卡片例句（复用桌面端逻辑）
        try:
            upcoming_keywords = main_logic._task_manager.get_upcoming_card_keywords(base_deck_name)
            main_logic._task_manager.reorganize_queue(upcoming_keywords)
        except Exception as e:
            print(f"[ContextFlow Web] 预取失败: {e}")
    else:
        # 缓存未命中，入队生成
        main_logic._task_manager.reorganize_queue(keyword)
        main_logic._update_showing_state("例句生成中...", "", keyword)
        sentence_html = get_web_front_html("例句生成中...", keyword)

    # 重写媒体 URL（例句模板中的 pycmd 等）
    sentence_html = rewrite_media_urls(sentence_html)

    # 正面只显示例句，不显示原始卡片
    return sentence_html


def _render_web_answer(card, original_answer_html):
    """
    Web 端答案面渲染：我们的例句+翻译 + 原始卡片背面（不含正面重复）。

    card.answer() 会包含 {{FrontSide}} 展开的正面内容，导致嵌套。
    所以我们直接取 answer_text（纯背面模板渲染结果），避免正面重复。
    """
    from . import main_logic
    from .card.card_template_manager import get_web_back_html

    sentence = main_logic.showing_sentence
    translation = main_logic.showing_translation
    keyword = main_logic.showing_keyword

    if not sentence or sentence == "例句生成中...":
        return rewrite_media_urls(original_answer_html)

    # 我们的 HTML：例句+翻译（不包含原始卡片）
    our_html = get_web_back_html(sentence, translation, "", keyword)
    our_html = rewrite_media_urls(our_html)

    # 原始卡片背面：用 CSS + answer_text
    # answer_text 是背面模板渲染结果，不含 CSS 包装，但包含 {{FrontSide}} 展开内容
    # 我们不能直接用 answer_text，因为 {{FrontSide}} 会把正面再显示一遍
    # 所以改用 original_answer_html，但要去掉其中与正面重复的部分
    # 最简单的方式：直接用 card.answer() 返回的完整内容（含CSS）
    # 然后去掉 {{FrontSide}} 带来的正面重复
    #
    # 实际上 card.answer() = <style>CSS</style>answer_text
    # answer_text 包含 {{FrontSide}} 展开的内容
    # 我们无法从 API 层面分离 {{FrontSide}} 和背面内容
    # 所以直接把 card.answer() 原样输出，让用户看到原始卡片的完整答案面
    original = rewrite_media_urls(original_answer_html)

    return our_html + original


# ── 卡片获取 ──────────────────────────────────────────────────

def get_next_card(mw) -> dict:
    """
    获取下一张卡片数据。
    返回三种状态之一：
      - {status: "card", card_id, question_html, css, button_labels, counts}
      - {status: "waiting", wait_seconds, learning_remaining}
      - {status: "finished"}
    """
    # 清除已过期卡片的计时记录
    _card_show_times.clear()

    card = mw.col.sched.getCard()
    if card:
        # getCard() 内部已调用 start_timer()，但我们在 Web 端额外记录
        # 展示时间戳，以便在 answer_card() 中使用真实学习时间。
        _card_show_times[card.id] = time.time()
        return _render_card_data(mw, card)

    # 队列为空，检查是否有等待中的学习中卡片
    deck_id = mw.col.decks.selected()
    deck_name = mw.col.decks.name(deck_id)
    learn_ids = mw.col.find_cards(f'deck:"{deck_name}" is:learn')

    if learn_ids:
        from anki.utils import int_time
        now = int_time()
        nearest_wait = float('inf')
        for cid in learn_ids:
            try:
                c = mw.col.get_card(cid)
                wait = c.due - now
                if wait < nearest_wait:
                    nearest_wait = wait
            except Exception:
                continue
        return {
            "status": "waiting",
            "wait_seconds": max(0, int(nearest_wait)),
            "learning_remaining": len(learn_ids),
        }

    return {"status": "finished"}


def _render_card_data(mw, card) -> dict:
    """将卡片渲染为 API 响应数据，一次性返回正面和背面。"""
    from . import main_logic
    from .card.card_template_manager import get_web_back_html
    from .config_manager import get_config

    states = mw.col._backend.get_scheduling_states(card.id)
    labels = mw.col._backend.describe_next_states(states)

    # 判断是否为目标牌组
    config = get_config()
    config_deck_name = config.get("deck_name")
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name
    current_deck = mw.col.decks.name(card.did)
    is_target = _is_target_deck(card, current_deck, base_deck_name)

    # 渲染 contextflow 例句正面（例句+翻译隐藏条）
    raw_question = card.question()
    question_html = _render_web_question(card, raw_question)

    # 原始卡片背面
    raw_answer = card.answer()
    origin_html = rewrite_media_urls(raw_answer)

    # 只有目标牌组才生成我们的例句背面
    sentence_back_html = ""
    if is_target:
        sentence = main_logic.showing_sentence
        translation = main_logic.showing_translation
        keyword = main_logic.showing_keyword
        if sentence and sentence != "例句生成中...":
            sentence_back_html = get_web_back_html(sentence, translation, "", keyword)
            sentence_back_html = rewrite_media_urls(sentence_back_html)

    css = card.render_output().css
    counts = mw.col.sched.counts(card)

    # 判断当前卡片类型：0=new, 1=learning, 2=review, 3=relearning
    # relearning 归入 learning 类别显示
    card_type = card.type
    if card_type == 0:
        active_type = "new"
    elif card_type in (1, 3):
        active_type = "learning"
    else:
        active_type = "review"

    return {
        "status": "card",
        "card_id": card.id,
        "question_html": question_html,
        "sentence_back_html": sentence_back_html,
        "origin_html": origin_html,
        "css": css,
        "button_labels": list(labels),
        "active_type": active_type,
        "counts": {
            "new": counts[0],
            "learning": counts[1],
            "review": counts[2],
        },
    }


# ── 答案获取 ──────────────────────────────────────────────────

def get_answer(mw, card_id: int) -> dict:
    """获取卡片答案面。分开返回我们的例句+翻译 和 原始卡片答案。"""
    from . import main_logic
    from .card.card_template_manager import get_web_back_html

    card = mw.col.get_card(card_id)

    sentence = main_logic.showing_sentence
    translation = main_logic.showing_translation
    keyword = main_logic.showing_keyword

    if not sentence or sentence == "例句生成中...":
        # 例句还没生成，返回原始答案
        raw_answer = card.answer()
        return {
            "sentence_html": "",
            "answer_html": rewrite_media_urls(raw_answer),
        }

    # 我们的例句+翻译（不含原始卡片）
    our_html = get_web_back_html(sentence, translation, "", keyword)
    our_html = rewrite_media_urls(our_html)

    # 原始卡片答案面
    raw_answer = card.answer()
    original = rewrite_media_urls(raw_answer)

    return {
        "sentence_html": our_html,
        "answer_html": original,
    }


# ── 答题 ──────────────────────────────────────────────────────

def answer_card(mw, card_id: int, ease: int) -> dict:
    """答题并返回下一张卡片数据。"""
    # 直接通过 card_id 获取卡片，避免再次调用 sched.getCard() 导致计时器重置。
    # sched.getCard() 内部会调用 start_timer()，会覆盖真实的查看时间。
    try:
        card = mw.col.get_card(card_id)
    except Exception:
        print(f"[ContextFlow Web] 卡片 {card_id} 获取失败，跳过答题")
        return get_next_card(mw)

    if not card:
        print(f"[ContextFlow Web] 卡片 {card_id} 不存在，跳过答题")
        return get_next_card(mw)

    # 恢复卡片首次展示时的计时起点，使 time_taken() 返回真实的 Web 学习时间。
    # get_next_card() 在获取卡片时已记录 _card_show_times。
    show_time = _card_show_times.pop(card_id, None)
    if show_time is not None:
        card.timer_started = show_time
    else:
        # 没有记录（可能是刷新后），用当前时间兜底
        card.start_timer()

    taken_ms = card.time_taken(capped=False)
    mw.col.sched.answerCard(card, ease)

    # Rust 后端对 preview/filtered 队列的卡片可能不写入 time，
    # 这里通过 SQL 直接修补 revlog 中最新记录的 time 字段。
    if taken_ms > 0:
        try:
            from anki.utils import int_time
            now_ms = int_time(1000)
            mw.col.db.execute(
                "UPDATE revlog SET time = ? WHERE cid = ? AND id > ?",
                taken_ms, card_id, now_ms - 60_000,  # 最近 60 秒内的记录
            )
        except Exception as e:
            print(f"[ContextFlow Web] revlog time 修补失败: {e}")
    return get_next_card(mw)


# ── 牌组操作 ──────────────────────────────────────────────────

def get_decks(mw) -> list:
    """获取牌组列表及其计数。"""
    tree = mw.col.sched.deck_due_tree()
    result = []
    _flatten_deck_tree(tree, result)
    return result


def _flatten_deck_tree(node, result: list, prefix: str = ""):
    """递归展平牌组树。"""
    name = f"{prefix}::{node.name}" if prefix else node.name
    if node.deck_id != 1:  # 跳过根节点
        result.append({
            "id": node.deck_id,
            "name": name,
            "new_count": node.new_count,
            "learning_count": node.learn_count,
            "review_count": node.review_count,
        })
    for child in node.children:
        child_prefix = name if node.deck_id != 1 else ""
        _flatten_deck_tree(child, result, child_prefix)


def select_deck(mw, deck_id: int) -> dict:
    """切换当前牌组。"""
    mw.col.decks.select(deck_id)
    return {"success": True, "deck_name": mw.col.decks.name(deck_id)}


def get_status(mw) -> dict:
    """获取当前状态信息。"""
    deck_id = mw.col.decks.selected()
    deck_name = mw.col.decks.name(deck_id)
    counts = mw.col.sched.counts()
    return {
        "deck_name": deck_name,
        "deck_id": deck_id,
        "new": counts[0],
        "learning": counts[1],
        "review": counts[2],
    }


def check_sentence_status(mw) -> dict:
    """
    检查当前卡片的例句是否已生成。
    用于手机端轮询：如果例句已就绪，返回新的问题面 HTML。
    """
    from . import main_logic
    from .cache.cache_manager import load_cache, pop_cache
    from .card.card_template_manager import get_processed_front_html
    from .config_manager import get_config

    keyword = main_logic.showing_keyword
    current_sentence = main_logic.showing_sentence

    # 如果没有等待中的关键词，或已经有例句了
    if not keyword or current_sentence != "例句生成中...":
        return {"ready": True if keyword and current_sentence else False}

    # 检查缓存是否已有
    cached = load_cache(keyword)
    if not cached:
        return {"ready": False}

    # 例句已就绪，生成新的 HTML
    popped_pair = pop_cache(keyword)
    if popped_pair:
        sentence, translation = popped_pair
        main_logic._update_showing_state(sentence, translation, keyword)

        # 如果缓存用尽，重新入队
        if not load_cache(keyword):
            main_logic._task_manager.reorganize_queue(keyword, is_repopulate=True)

        # 需要重新获取当前卡片来渲染
        card = mw.col.sched.getCard()
        if card:
            raw_question = card.question()
            # 直接渲染带例句的问题面（这次会命中缓存）
            question_html = _render_web_question(card, raw_question)
            return {
                "ready": True,
                "question_html": question_html,
            }

    return {"ready": False}
