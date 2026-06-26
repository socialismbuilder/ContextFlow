// ── SSE 流式读取（AI 对话）────────────────────────────────
// 后端 POST /api/ai/chat 返回 text/event-stream：
//   data: {"type":"delta","content":"..."}\n\n
//   data: {"type":"error","message":"..."}\n\n
//   data: {"type":"done"}\n\n
// 用 fetch + ReadableStream 读取（POST 不能用 EventSource）。
// 取代原 AiBottomSheet IIFE 里的 startStream / handleSseEvent。

import { AI_CHAT_URL } from '../api/client.js';

/**
 * 流式发起 AI 对话。
 * @param {object}   body   {sentence, word, history}
 * @param {function} onDelta (content) 每收到增量文本
 * @param {function} onError (message) 收到错误事件
 * @param {function} onDone  () 流正常结束
 * @param {AbortSignal} signal 可选，用于中断（关闭抽屉时）
 */
export async function streamChat({ sentence, word, history }, { onDelta, onError, onDone }, signal) {
    let resp;
    try {
        resp = await fetch(AI_CHAT_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sentence, word, history }),
            signal,
        });
    } catch (e) {
        if (e.name === 'AbortError') return;
        onError('连接失败：' + e.message);
        return;
    }
    if (!resp.ok || !resp.body) {
        onError('服务器返回错误 (HTTP ' + resp.status + ')');
        return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    async function processEvent(rawEvent) {
        // 取 data: 行
        const lines = rawEvent.split('\n');
        for (const line of lines) {
            const trimmed = line.trimStart();
            if (!trimmed.startsWith('data:')) continue;
            const payload = trimmed.slice(5).trim();
            if (!payload) continue;
            let evt;
            try {
                evt = JSON.parse(payload);
            } catch {
                continue;
            }
            if (evt.type === 'delta' && evt.content != null) {
                onDelta(evt.content);
            } else if (evt.type === 'error') {
                onError(evt.message || 'AI 错误');
                return true; // 错误后流结束
            }
            // type === 'done'：正常结束，循环自然终止
        }
        return false;
    }

    try {
        while (true) {
            if (signal?.aborted) break;
            const { done, value } = await reader.read();
            if (done) {
                // 处理残余 buffer
                if (buffer.trim()) await processEvent(buffer);
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            // SSE 事件以空行分隔
            let idx;
            while ((idx = buffer.indexOf('\n\n')) >= 0) {
                const rawEvent = buffer.slice(0, idx);
                buffer = buffer.slice(idx + 2);
                const stop = await processEvent(rawEvent);
                if (stop) return;
            }
        }
        onDone?.();
    } catch (e) {
        if (e.name !== 'AbortError') {
            onError('流读取失败：' + e.message);
        }
    }
}
