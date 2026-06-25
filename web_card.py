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
_card_show_times: dict[int, float] = {}  # card_id -> time.time()


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


def _is_saved_deck(card, current_deck, save_deck_name):
    """判断卡片是否属于保存例句牌组且为正面（ord==0）"""
    if not save_deck_name:
        return False
    return (current_deck == save_deck_name or current_deck.startswith(save_deck_name + "::")) and card.ord == 0


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


def _clean_word(kw: str) -> str:
    """清洗关键词用于朗读：去掉括号注释（如 'word(动词)' → 'word'）。"""
    word = re.sub(r'[（(].*?[）)]', '', kw).strip()
    return word if word else kw


def _strip_sound_tags(text: str) -> str:
    """轻量清洗：只去掉 [sound:...] 等方括号媒体标签，保留 <u> 等标记。
    （<u> 用于高亮目标词，前端 highlightHtml 会受控解析为高亮 span，安全。）
    """
    import html as _html
    no_sound = re.sub(r'\[sound:[^\]]*\]', '', text)
    return _html.unescape(no_sound).strip()


def _extract_saved_sentence(card):
    """
    从保存例句卡的 note 读取例句对（fields[0]=例句, fields[1]=翻译）。
    保留 <u> 高亮标记（前端受控渲染），只清洗 [sound:] 等媒体标签。
    返回 (sentence, translation) 或 None。
    """
    try:
        note = card.note()
        if not note.fields or len(note.fields) < 2:
            return None
        sentence = _strip_sound_tags(note.fields[0])
        translation = _strip_sound_tags(note.fields[1])
        if not sentence:
            return None
        return (sentence, translation)
    except Exception:
        return None


def _prepare_target_sentence(card, base_deck_name, field_index_match):
    """
    目标牌组（target）例句准备：从缓存取例句对，返回结构化数据。

    不再生成 HTML——只返回例句对 + 关键词 + 就绪状态，前端自行渲染。
    命中缓存：更新全局显示状态、缓存用尽时入队、预取后续卡片（业务逻辑全部保留）。
    未命中：入队生成，标记 ready=False，前端轮询。
    """
    from .cache.cache_manager import pop_cache, load_cache
    from . import main_logic

    keyword = _extract_keyword(card, field_index_match)
    if not keyword:
        return None

    # 朗读用纯词（去括号注释）
    speak_keyword = _clean_word(keyword)

    popped_pair = pop_cache(keyword)
    if popped_pair:
        sentence, translation = popped_pair
        # 更新全局显示状态（复用 main_logic 的状态管理）
        main_logic._update_showing_state(sentence, translation, keyword)
        # 如果缓存用尽，重新入队
        if not load_cache(keyword):
            main_logic._task_manager.reorganize_queue(keyword, is_repopulate=True)

        # 预取后续卡片例句（复用桌面端逻辑）
        try:
            upcoming_keywords = main_logic._task_manager.get_upcoming_card_keywords(base_deck_name)
            main_logic._task_manager.reorganize_queue(upcoming_keywords)
        except Exception as e:
            print(f"[ContextFlow Web] 预取失败: {e}")

        return {
            "sentence": sentence,
            "translation": translation,
            "keyword": speak_keyword,
            "ready": True,
        }

    # 缓存未命中，入队生成
    main_logic._task_manager.reorganize_queue(keyword)
    main_logic._update_showing_state("例句生成中...", "", keyword)
    return {
        "sentence": "例句生成中...",
        "translation": "",
        "keyword": speak_keyword,
        "ready": False,
    }


# ── 卡片获取 ──────────────────────────────────────────────────

def _kind_to_active_type(nkind) -> str:
    """将 SchedulingState.Normal 的 oneof kind 映射为高亮类型。"""
    if nkind == "new":
        return "new"
    if nkind == "learning":
        return "learning"
    # review / relearning(lapsed review) / None → review
    return "review"


def _active_type_from_states(mw, states, card) -> str:
    """
    推断当前卡片的高亮类型（new/learning/review），与 Anki 顶部
    new/learning/review 计数归类保持一致——这样高亮标签和答题后
    减少的计数值落在同一栏。

    不能直接用 card.queue / card.type：
      - 自定义学习（过滤牌组）会把卡借出，其 card.queue 被改写为 4（preview），
        原本的"学习中"信息从 card 对象上丢失；
      - card.type 是卡片身份（new/learning/review/relearning），不能反映
        "当前是否处在学习步进"，普通到期复习卡 type 也是 2。
    因此改用调度器 get_queued_cards() 里这张卡的 queue 枚举
    （NEW=0 / LEARNING=1 / REVIEW=2）——这是 Anki 自己累加顶部计数用的归类，
    过滤牌组下也准确。

    回退链：queued 枚举 → states.current（rescheduling 的 original_state）→ card.queue。
    """
    # 主路径：调度器队列归类
    try:
        for q in mw.col.sched.get_queued_cards().cards:
            if q.card.id == card.id:
                # NEW=0, LEARNING=1, REVIEW=2
                if q.queue == 0:
                    return "new"
                if q.queue == 1:
                    return "learning"
                return "review"
    except Exception as e:
        print(f"[ContextFlow Web] get_queued_cards 查询失败: {e}")

    # 回退 1：rescheduling 过滤牌组用原始调度类型
    try:
        cur = states.current
        if cur.WhichOneof("kind") == "filtered":
            filt = cur.filtered
            if filt.WhichOneof("kind") == "rescheduling":
                return _kind_to_active_type(
                    filt.rescheduling.original_state.WhichOneof("kind"))
    except Exception:
        pass

    # 回退 2：card.queue（普通牌组场景）
    queue = card.queue
    if queue == 0:
        return "new"
    if queue in (1, 3):
        return "learning"
    return "review"


def get_next_card(mw) -> dict:
    """
    获取下一张卡片数据。
    返回三种状态之一：
      - {status: "card", card_id, question_html, css, button_labels, counts}
      - {status: "waiting", wait_seconds, learning_remaining}
      - {status: "finished"}
    """
    _card_show_times.clear()

    card = mw.col.sched.getCard()
    if card:
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
    """
    将卡片渲染为 API 响应数据。

    三种模式（card_mode）：
      - target：目标牌组，注入 ContextFlow 例句（发例句对+关键词+就绪状态，前端渲染）
      - saved： 保存例句牌组，直接读 note 字段（发例句对，无关键词）
      - plain： 普通牌组，发渲染好的 Anki HTML，前端直接展示

    正面与背面共用同一份例句数据，前端根据 showTranslation 切换渲染。
    """
    from .config_manager import get_config

    states = mw.col._backend.get_scheduling_states(card.id)
    labels = mw.col._backend.describe_next_states(states)

    config = get_config()
    config_deck_name = config.get("deck_name") or ""
    save_deck_name = config.get("save_deck") or ""
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name
    current_deck = mw.col.decks.name(card.did)

    # 按三模式分流
    sentence = ""
    translation = ""
    keyword = ""
    sentence_ready = True
    question_html = ""

    if _is_target_deck(card, current_deck, base_deck_name):
        card_mode = "target"
        data = _prepare_target_sentence(card, base_deck_name, field_index_match)
        if data is None:
            # 提取关键词失败，回退为普通牌组渲染
            card_mode = "plain"
        else:
            sentence = data["sentence"]
            translation = data["translation"]
            keyword = data["keyword"]
            sentence_ready = data["ready"]
    elif _is_saved_deck(card, current_deck, save_deck_name):
        saved = _extract_saved_sentence(card)
        if saved:
            card_mode = "saved"
            sentence, translation = saved
        else:
            card_mode = "plain"
    else:
        card_mode = "plain"

    if card_mode == "plain":
        question_html = rewrite_media_urls(card.question())

    # 原始卡片背面（三种模式都要，翻面时显示）
    origin_html = rewrite_media_urls(card.answer())

    counts = mw.col.sched.counts(card)

    # 判断当前卡片类型用于高亮（new/learning/review）。
    # 用调度器给出的 states.current（Anki 翻面高亮计数的同一数据源），
    # 而不是 card.queue/card.type —— 后两者在过滤牌组（自定义学习）里会失真：
    # 自定义学习会把学习中卡借出进 cram 牌组，其 queue 常被当作 review(2)，
    # 导致学习卡被误高亮成"待复习"。
    active_type = _active_type_from_states(mw, states, card)

    return {
        "status": "card",
        "card_id": card.id,
        "card_mode": card_mode,
        "sentence": sentence,
        "translation": translation,
        "keyword": keyword,
        "sentence_ready": sentence_ready,
        "question_html": question_html,
        "origin_html": origin_html,
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
    """
    获取卡片答案面（/api/card/show 的 fallback）。

    返回当前显示状态的例句对（结构化，前端自行渲染）+ 原始卡片背面 HTML。
    例句数据取自 main_logic.showing_*（由 _prepare_target_sentence 同步写入）。
    """
    from . import main_logic

    card = mw.col.get_card(card_id)

    sentence = main_logic.showing_sentence
    translation = main_logic.showing_translation
    keyword = main_logic.showing_keyword

    raw_answer = card.answer()
    original = rewrite_media_urls(raw_answer)

    if not sentence or sentence == "例句生成中...":
        # 例句还没生成，只返回原始答案
        return {
            "sentence": "",
            "translation": "",
            "keyword": "",
            "answer_html": original,
        }

    return {
        "sentence": sentence,
        "translation": translation,
        "keyword": _clean_word(keyword) if keyword else "",
        "answer_html": original,
    }


# ── 答题 ──────────────────────────────────────────────────────

def answer_card(mw, card_id: int, ease: int) -> dict:
    """答题并返回下一张卡片数据。"""
    # 确认卡片在队列顶部
    top_card = mw.col.sched.getCard()
    if not top_card or top_card.id != card_id:
        # 卡片不在队列顶部，可能已被处理，跳过答题直接返回下一张
        print(f"[ContextFlow Web] 卡片 {card_id} 不在队列顶部，跳过答题")
        return get_next_card(mw)

    # 用卡片展示时间作为 timer_started，让 answerCard 内部的 time_taken() 返回真实时长
    show_time = _card_show_times.pop(card_id, None)
    if show_time is not None:
        top_card.timer_started = show_time
    else:
        top_card.start_timer()

    mw.col.sched.answerCard(top_card, ease)
    return get_next_card(mw)


# ── 重新生成例句 ──────────────────────────────────────────────

def refresh_sentence(mw) -> dict:
    """
    重新生成当前卡片的例句（与桌面端 on_card_render 逻辑一致）：
      - 从缓存取下一条（pop_cache），命中则直接显示；
      - 未命中则重新入队生成，显示"例句生成中..."，前端轮询；
      - 重置卡片展示时间（重新计时）。
    """
    from .config_manager import get_config

    card = mw.col.sched.getCard()
    if not card:
        return {"status": "error", "error": "没有当前卡片"}

    config = get_config()
    config_deck_name = config.get("deck_name")
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name
    current_deck = mw.col.decks.name(card.did)

    if not _is_target_deck(card, current_deck, base_deck_name):
        return {"status": "error", "error": "当前卡片不属于例句牌组"}

    keyword = _extract_keyword(card, field_index_match)
    if not keyword:
        return {"status": "error", "error": "无法提取关键词"}

    # 重置展示时间，让答题时 time_taken() 从刷新时刻重新计时
    _card_show_times[card.id] = time.time()

    # 重新准备例句：_render_card_data 的 target 分支会 pop_cache 取下一条，
    # 命中则直接返回新例句对，未命中则入队生成并返回 ready=False（前端轮询）
    return _render_card_data(mw, card)


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


def get_undo_status(mw) -> dict:
    """获取撤回状态。"""
    status = mw.col.undo_status()
    return {"can_undo": bool(status.undo), "undo_name": status.undo or ""}


def undo_card(mw) -> dict:
    """撤回上一次答题操作，返回下一张卡片数据。"""
    from anki.errors import UndoEmpty

    status = mw.col.undo_status()
    if not status.undo:
        return {"status": "error", "error": "没有可撤回的操作"}

    try:
        mw.col.undo()
        return get_next_card(mw)
    except UndoEmpty:
        return {"status": "error", "error": "没有可撤回的操作"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


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
    检查当前卡片的例句是否已生成（仅 target 牌组轮询用）。
    例句就绪时返回结构化例句对 + 关键词，前端自行渲染。
    """
    from . import main_logic
    from .cache.cache_manager import load_cache, pop_cache

    keyword = main_logic.showing_keyword
    current_sentence = main_logic.showing_sentence

    # 如果没有等待中的关键词，或已经有例句了
    if not keyword or current_sentence != "例句生成中...":
        return {"ready": True if keyword and current_sentence else False}

    # 检查缓存是否已有
    cached = load_cache(keyword)
    if not cached:
        return {"ready": False}

    # 例句已就绪：取出并直接返回（不再二次 pop_cache，避免丢弃刚取出的例句）
    popped_pair = pop_cache(keyword)
    if popped_pair:
        sentence, translation = popped_pair
        main_logic._update_showing_state(sentence, translation, keyword)

        # 如果缓存用尽，重新入队
        if not load_cache(keyword):
            main_logic._task_manager.reorganize_queue(keyword, is_repopulate=True)

        return {
            "ready": True,
            "sentence": sentence,
            "translation": translation,
            "keyword": _clean_word(keyword),
        }

    return {"ready": False}
