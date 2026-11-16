# -*- coding: utf-8 -*-
"""
把「卡片平均用时」模块按原生统计的样式注入到 Anki 原生统计页中。

原理：原生统计页是一个 WebView 里跑的 Svelte 应用，图表卡片由
`div.container ... svelte-zuiu8u` 包裹。我们复用同样的 class 组合构建一个
新卡片（每天平均用时的条形图 + 范围切换 + 悬浮提示 + 底部 总计/平均/中位数
统计行），追加到图表列表最后，并通过 JS 轮询在 Svelte 重渲染抹掉卡片时
自动补回。

图表为 SVG 手绘（viewBox 600x250、bars/hover-columns/刻度结构均照抄原生），
坐标轴刻度复用 x-ticks/y-ticks 样式类，底部统计行复用 svelte-19er4xn 类。
数据口径沿用原自定义统计：日界凌晨 4 点，过滤 time < 1ms，按牌组名匹配子牌组。
"""

import json
import os
from datetime import date, datetime, timedelta

from aqt import gui_hooks, mw
from aqt.webview import AnkiWebView

# 范围选项：label -> (覆盖天数(0=全部历史), 每柱天数(0=自动，控制在100柱以内))
_RADIO_OPTIONS = [
    ("1 个月", 30, 1),
    ("3 个月", 90, 1),
    ("1 年", 365, 5),
    ("全部时间", 0, 0),
]
DEFAULT_RADIO_INDEX = 2  # 默认 1 年

MAX_BARS = 100  # 任意范围下最多渲染的柱子数

_JS_FILE = os.path.join(os.path.dirname(__file__), "avg_time.js")
_JS_TEMPLATE_CACHE = None


def _load_js_template() -> str:
    """读取注入脚本模板（ui/avg_time.js），带缓存"""
    global _JS_TEMPLATE_CACHE
    if _JS_TEMPLATE_CACHE is None:
        try:
            with open(_JS_FILE, "r", encoding="utf-8") as f:
                _JS_TEMPLATE_CACHE = f.read()
        except Exception as e:
            print(f"[avg_time] 读取注入脚本模板失败: {e}")
            _JS_TEMPLATE_CACHE = ""
    return _JS_TEMPLATE_CACHE



def _attr_title(webview) -> str:
    """AnkiWebView 用普通 str 属性遮了 title，兼容属性/方法两种形态"""
    try:
        value = getattr(webview, "title", None)
        if callable(value):
            value = value()
        return (value or "").lower()
    except Exception:
        return ""


def _find_native_stats_webview(statsdialog):
    """找到原生统计页对应的 WebView（title 里带 stats 的那个）"""
    try:
        webviews = statsdialog.findChildren(AnkiWebView)
    except RuntimeError:
        return None

    matched = [w for w in webviews if "stats" in _attr_title(w)
               and not _attr_title(w).startswith("default")]
    if matched:
        return matched[0]
    others = [w for w in webviews if not _attr_title(w).startswith("default")]
    return others[0] if others else None


def _deck_ids_for(deck_name: str) -> list:
    deck = mw.col.decks.by_name(deck_name)
    if not deck:
        return []
    return [d["id"] for d in mw.col.decks.all() if deck_name in d["name"]]


def _study_days_for_deck(deck_name: str, days_back) -> dict:
    """按 4 点分界聚合该牌组的复习数据 -> {date: (卡片数, 总秒数)}

    days_back 为 None 时聚合全部历史。
    """
    if mw is None or mw.col is None:
        return {}
    try:
        deck_ids = _deck_ids_for(deck_name)
        if not deck_ids:
            return {}

        where_time = ""
        if days_back is not None:
            today_4am = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=4)
            start_ts = int((today_4am - timedelta(days=days_back)).timestamp() * 1000)
            where_time = f"AND id >= {start_ts}"

        query = f"""
            SELECT strftime('%Y-%m-%d', datetime((id/1000)-14400, 'unixepoch', 'localtime')) AS d,
                   COUNT(*) AS cards,
                   SUM(time)/1000.0 AS secs
            FROM revlog
            WHERE cid IN (
                SELECT id FROM cards WHERE did IN ({','.join(str(i) for i in deck_ids)})
            ) {where_time}
            AND time > 1
            GROUP BY d
        """
        per_day = {}
        for day, cards, secs in mw.col.db.execute(query):
            try:
                per_day[date.fromisoformat(day)] = (cards, secs or 0.0)
            except ValueError:
                pass
        return per_day
    except Exception as e:
        print(f"[avg_time] 查询统计失败: {e}")
        return {}


def _range_stats(deck_name: str, days_back) -> dict:
    """单个范围的汇总：{cards, seconds, median}（median 为逐条复习用时中位数，秒）"""
    if mw is None or mw.col is None:
        return {"cards": 0, "seconds": 0.0, "median": None}
    try:
        deck_ids = _deck_ids_for(deck_name)
        if not deck_ids:
            return {"cards": 0, "seconds": 0.0, "median": None}

        where_time = ""
        if days_back is not None:
            today_4am = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=4)
            start_ts = int((today_4am - timedelta(days=days_back)).timestamp() * 1000)
            where_time = f"AND id >= {start_ts}"

        where = (
            f"cid IN (SELECT id FROM cards WHERE did IN ({','.join(str(i) for i in deck_ids)})) "
            f"{where_time} AND time > 1"
        )

        row = mw.col.db.first(f"SELECT COUNT(*), COALESCE(SUM(time)/1000.0, 0) FROM revlog WHERE {where}")
        cards = int(row[0]) if row else 0
        seconds = float(row[1]) if row else 0.0

        median = None
        if cards > 0:
            if cards % 2 == 1:
                q = (f"SELECT AVG(time)/1000.0 FROM (SELECT time FROM revlog WHERE {where} "
                     f"ORDER BY time LIMIT 1 OFFSET {cards // 2})")
            else:
                q = (f"SELECT AVG(time)/1000.0 FROM (SELECT time FROM revlog WHERE {where} "
                     f"ORDER BY time LIMIT 2 OFFSET {cards // 2 - 1})")
            mrow = mw.col.db.first(q)
            if mrow and mrow[0] is not None:
                median = float(mrow[0])

        return {"cards": cards, "seconds": seconds, "median": median}
    except Exception as e:
        print(f"[avg_time] 查询范围统计失败: {e}")
        return {"cards": 0, "seconds": 0.0, "median": None}


def _build_series(deck_name: str) -> list:
    """按天生成图表数据（最旧在前）：[{d: 'YYYY-MM-DD', s: 平均秒或null, n: 卡片数, t: 总秒}]"""
    per_day = _study_days_for_deck(deck_name, None)  # 全部历史
    today = date.today()
    if per_day:
        first = min(per_day)
    else:
        first = today  # 无数据时也至少生成一天，保证前端有窗口
    series = []
    d = first
    while d <= today:
        cards, secs = per_day.get(d, (0, 0.0))
        series.append({
            "d": d.isoformat(),
            "s": round(secs / cards, 1) if cards > 0 else None,
            "n": int(cards),
            "t": round(secs, 1),
        })
        d += timedelta(days=1)
    return series


def _eval_js(statsdialog, js: str) -> None:
    webview = _find_native_stats_webview(statsdialog)
    if webview is None:
        print("[avg_time] 未找到原生统计 WebView，跳过注入")
        return
    try:
        page = webview.page()

        def _on_ran(result):
            print(f"[avg_time] 注入脚本执行返回: {result!r} (None 通常代表脚本抛错或页面尚未就绪)")

        def _on_check(exists):
            print(f"[avg_time] DOM 检查: 卡片存在={exists}")

        def _verify():
            try:
                webview.page().runJavaScript(
                    "!!document.getElementById('cf-avg-time-card')", 0, _on_check)
            except Exception as e:
                print(f"[avg_time] DOM 检查失败: {e}")

        try:
            page.runJavaScript(js + ";window.__cfAvgTimeStatus || 'executed'", 0, _on_ran)
        except Exception as e:
            print(f"[avg_time] runJavaScript 失败: {e}，回退 eval")
            try:
                webview.eval(js)
            except Exception as e2:
                print(f"[avg_time] eval 也失败: {e2}")

        mw.progress.single_shot(5000, _verify)
    except RuntimeError:
        print("[avg_time] WebView 已销毁，注入取消")


def inject_avg_time_on_open(statsdialog) -> None:
    """stats_dialog_will_show 钩子入口"""
    try:
        deck = mw.col.decks.current()
        deck_name = deck["name"] if deck else "未知牌组"
    except Exception:
        deck_name = "未知牌组"

    payload = {
        "deck": deck_name,
        "todayYear": date.today().year,
        "series": _build_series(deck_name),
        "ranges": [dict(label=label, **_range_stats(deck_name, days if days > 0 else None))
                   for label, days, _bar in _RADIO_OPTIONS],
    }
    options = [{"label": label, "days": days, "barDays": bar}
               for label, days, bar in _RADIO_OPTIONS]

    template = _load_js_template()
    if not template:
        return

    js = (template
          .replace("__DATA__", json.dumps(payload, ensure_ascii=False))
          .replace("__OPTIONS__", json.dumps(options, ensure_ascii=False))
          .replace("__DEFAULT__", str(DEFAULT_RADIO_INDEX))
          .replace("__MAXBARS__", str(MAX_BARS)))

    # 页面加载需要时间；JS 内部还会自旋重试，这里错开几个时机保险
    for delay_ms in (3000, 8000, 15000):
        mw.progress.single_shot(delay_ms, lambda: _eval_js(statsdialog, js))

    print(f"[avg_time] 已调度『卡片平均用时』模块注入（牌组: {deck_name}）")
