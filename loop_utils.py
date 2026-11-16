# -*- coding: utf-8 -*-
"""
asyncio 事件循环的创建/关闭兜底工具。

背景：Windows 上 `asyncio.new_event_loop()` 创建的是 ProactorEventLoop，
其 `__init__` 里第一件事就是 `socket.socketpair()` 建 self-pipe。这一步
一旦失败（WinError 10013=被杀软/防火墙拒绝、10048=端口耗尽、
10055=socket 缓冲/资源耗尽），会留下一个半成品 loop 对象；它被垃圾回收
时会在 `__del__` → `close()` → `_close_self_pipe()` 里炸出：

    AttributeError: 'ProactorEventLoop' object has no attribute '_ssock'

这条报错出现在 Anki 退出日志里，本身无害，但它是"某次 loop 创建失败"
的遗言，真正的第一现场（OSError: WinError ...）反而被淹没。所以统一走
safe_new_loop()：把失败拦在源头，打出可读的日志并返回 None。
"""

import asyncio
import threading


def safe_new_loop(tag: str):
    """创建新事件循环；失败时打日志并返回 None，绝不留下半成品对象。"""
    try:
        return asyncio.new_event_loop()
    except Exception as e:
        print(
            f"[{tag}] 错误: 创建 asyncio 事件循环失败"
            f"（常见于 WinError 10013/10048/10055，检查杀软/防火墙或 socket 资源占用）: {e}"
        )
        return None


def close_loop(loop, tag: str) -> None:
    """尽力关闭事件循环（先收掉 asyncgen，再 close），失败只打警告不抛。

    注意：loop 必须已停止运行（run_forever/run_until_complete 已返回），
    否则请先用 call_soon_threadsafe(loop.stop) 停掉它。
    """
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    except Exception as e:
        print(f"[{tag}] 警告: shutdown_asyncgens 失败: {e}")
    try:
        loop.close()
    except Exception as e:
        print(f"[{tag}] 警告: 关闭事件循环失败: {e}")


def stop_loop_threadsafe(loop, tag: str) -> None:
    """从其他线程安全地请求事件循环停止（run_forever 返回）。"""
    try:
        loop.call_soon_threadsafe(loop.stop)
    except RuntimeError as e:
        # loop 已关闭/线程已死时 call_soon_threadsafe 会抛 RuntimeError
        print(f"[{tag}] 警告: 请求事件循环停止失败（可能已退出）: {e}")
