# -*- coding: utf-8 -*-
"""
Web 服务器 —— 基于 aiohttp 的局域网复习后端。
手机浏览器通过此服务获取卡片、答题、播放媒体。
"""

import json
import os
import threading
import mimetypes
import concurrent.futures
from pathlib import Path

from aiohttp import web

from . import web_card

# ── 全局状态 ──────────────────────────────────────────────────

_server_thread: threading.Thread | None = None
_runner: web.AppRunner | None = None
_aiohttp_loop = None


def start(mw, port: int = 8765):
    """启动 Web 服务器（后台线程）。"""
    global _server_thread, _runner, _aiohttp_loop

    if _runner is not None:
        print("[ContextFlow Web] 服务器已在运行")
        return

    app = _create_app(mw)
    _server_thread = threading.Thread(
        target=_run_server,
        args=(app, port),
        name="ContextFlowWebServer",
        daemon=True,
    )
    _server_thread.start()
    print(f"[ContextFlow Web] 服务器启动中 (端口 {port})...")


def stop():
    """停止 Web 服务器。"""
    global _runner, _server_thread, _aiohttp_loop
    if _aiohttp_loop is not None:
        _aiohttp_loop.call_soon_threadsafe(_aiohttp_loop.stop)
    if _runner is not None:
        _runner = None
    _server_thread = None
    _aiohttp_loop = None
    print("[ContextFlow Web] 服务器已停止")


def _run_server(app: web.Application, port: int):
    """在后台线程中运行 aiohttp 服务器。"""
    global _runner, _aiohttp_loop
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _aiohttp_loop = loop

    _runner = web.AppRunner(app)
    loop.run_until_complete(_runner.setup())

    site = web.TCPSite(_runner, "0.0.0.0", port)
    loop.run_until_complete(site.start())
    print(f"[ContextFlow Web] 服务器已启动: http://0.0.0.0:{port}")

    try:
        loop.run_forever()
    except Exception:
        pass
    finally:
        loop.run_until_complete(_runner.cleanup())
        loop.close()


# ── 线程安全桥接 ──────────────────────────────────────────────

def _run_on_main(mw, func, timeout=15):
    """在 Qt 主线程执行 func 并返回结果。"""
    future = concurrent.futures.Future()

    def wrapper():
        try:
            result = func()
            future.set_result(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            future.set_exception(e)

    mw.taskman.run_on_main(wrapper)
    return future.result(timeout=timeout)


# ── 创建 App ──────────────────────────────────────────────────

def _create_app(mw) -> web.Application:
    app = web.Application(client_max_size=10 * 1024 * 1024)
    app["mw"] = mw

    # API 路由
    app.router.add_get("/api/status", _handle_status)
    app.router.add_get("/api/decks", _handle_decks)
    app.router.add_post("/api/deck/select", _handle_deck_select)
    app.router.add_get("/api/card/next", _handle_card_next)
    app.router.add_get("/api/card/show", _handle_card_show)
    app.router.add_post("/api/card/answer", _handle_card_answer)
    app.router.add_get("/api/card/sentence", _handle_card_sentence)
    app.router.add_get("/api/tts/{text:.*}", _handle_tts)

    # 媒体文件
    app.router.add_get("/media/{path:.*}", _handle_media)

    # 静态文件（手机 UI）
    static_dir = os.path.join(os.path.dirname(__file__), "web", "static")
    if os.path.isdir(static_dir):
        app.router.add_static("/static", static_dir, name="static")
        # 根路径返回 index.html
        async def _handle_index(request):
            return web.FileResponse(os.path.join(static_dir, "index.html"))
        app.router.add_get("/", _handle_index)

    return app


# ── API 处理器 ────────────────────────────────────────────────

async def _handle_status(request: web.Request) -> web.Response:
    mw = request.app["mw"]
    data = _run_on_main(mw, lambda: web_card.get_status(mw))
    return web.json_response(data)


async def _handle_decks(request: web.Request) -> web.Response:
    mw = request.app["mw"]
    data = _run_on_main(mw, lambda: web_card.get_decks(mw))
    return web.json_response(data)


async def _handle_deck_select(request: web.Request) -> web.Response:
    mw = request.app["mw"]
    body = await request.json()
    deck_id = body.get("deck_id")
    if not deck_id:
        return web.json_response({"error": "缺少 deck_id"}, status=400)
    data = _run_on_main(mw, lambda: web_card.select_deck(mw, int(deck_id)))
    return web.json_response(data)


# ── 会话状态：记录当前卡片 ID ─────────────────────────────────

_session = {
    "current_card_id": None,
}


async def _handle_card_next(request: web.Request) -> web.Response:
    mw = request.app["mw"]
    try:
        data = _run_on_main(mw, lambda: web_card.get_next_card(mw))
        if data.get("status") == "card":
            _session["current_card_id"] = data["card_id"]
        return web.json_response(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e), "traceback": traceback.format_exc()}, status=500)


async def _handle_card_show(request: web.Request) -> web.Response:
    mw = request.app["mw"]
    card_id = _session.get("current_card_id")
    if not card_id:
        return web.json_response({"error": "没有当前卡片"}, status=400)
    data = _run_on_main(mw, lambda: web_card.get_answer(mw, card_id))
    return web.json_response(data)


async def _handle_card_answer(request: web.Request) -> web.Response:
    mw = request.app["mw"]
    body = await request.json()
    card_id = body.get("card_id")
    ease = body.get("ease")
    if not card_id or not ease:
        return web.json_response({"error": "缺少 card_id 或 ease"}, status=400)
    data = _run_on_main(mw, lambda: web_card.answer_card(mw, int(card_id), int(ease)))
    if data.get("status") == "card":
        _session["current_card_id"] = data["card_id"]
    else:
        _session["current_card_id"] = None
    return web.json_response(data)


async def _handle_card_sentence(request: web.Request) -> web.Response:
    """检查当前卡片的例句是否已生成。用于手机端轮询。"""
    mw = request.app["mw"]
    data = _run_on_main(mw, lambda: web_card.check_sentence_status(mw))
    return web.json_response(data)


# ── TTS 服务 ──────────────────────────────────────────────────

async def _handle_tts(request: web.Request) -> web.Response:
    """生成 TTS 音频并返回 MP3。"""
    import tempfile
    text = request.match_info["text"]
    if not text:
        return web.json_response({"error": "缺少文本"}, status=400)

    def _generate_tts():
        from .tts.tts_manager import tts_manager
        result = tts_manager.generate(text)
        if result:
            audio_data, ext = result
            return audio_data
        return None

    try:
        audio_data = _run_on_main(request.app["mw"], _generate_tts)
    except Exception:
        audio_data = None

    # 如果主线程生成失败，在后台线程尝试（edge-tts 不需要主线程）
    if audio_data is None:
        try:
            from .tts.tts_manager import tts_manager
            audio_data = tts_manager.generate(text)
            if audio_data:
                audio_data = audio_data[0]
        except Exception as e:
            return web.json_response({"error": f"TTS 生成失败: {e}"}, status=500)

    if audio_data is None:
        return web.json_response({"error": "TTS 生成失败"}, status=500)

    return web.Response(
        body=audio_data,
        content_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── 媒体文件服务 ──────────────────────────────────────────────

async def _handle_media(request: web.Request) -> web.Response:
    """从 Anki 媒体目录提供文件。"""
    mw = request.app["mw"]
    rel_path = request.match_info["path"]

    media_dir = _run_on_main(mw, lambda: mw.col.media.dir())
    if not media_dir:
        return web.json_response({"error": "媒体目录不可用"}, status=500)

    # 安全检查：防止路径遍历
    file_path = os.path.normpath(os.path.join(media_dir, rel_path))
    if not file_path.startswith(os.path.normpath(media_dir)):
        return web.json_response({"error": "禁止访问"}, status=403)

    if not os.path.isfile(file_path):
        return web.json_response({"error": "文件不存在"}, status=404)

    # 确定 MIME type
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    return web.FileResponse(file_path, headers={"Content-Type": mime_type})
