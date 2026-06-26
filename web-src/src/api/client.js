// ── API 客户端 ────────────────────────────────────────────
// 镜像后端 web_server.py 的全部端点，契约保持完全一致。
// 所有 POST 用 JSON，错误统一 {error} 信封（由调用方处理）。

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function getJSON(resp) {
    let data;
    try {
        data = await resp.json();
    } catch (e) {
        throw new Error(`响应解析失败 (HTTP ${resp.status})`);
    }
    return data;
}

// 统一 fetch + json，抛出异常供上层 catch
async function request(method, url, body) {
    const opts = { method };
    if (body !== undefined) {
        opts.headers = JSON_HEADERS;
        opts.body = JSON.stringify(body);
    }
    let resp;
    try {
        resp = await fetch(url, opts);
    } catch (e) {
        throw new Error(`无法连接到服务器，请确保 Anki 正在运行。\n${e.message}`);
    }
    return getJSON(resp);
}

// ── 状态 / 牌组 ──────────────────────────────────────────
// GET /api/status -> {deck_name, deck_id, new, learning, review, learning_language}
export const getStatus = () => request('GET', '/api/status');

// GET /api/decks -> [{id, name, new_count, learning_count, review_count}]
export const getDecks = () => request('GET', '/api/decks');

// POST /api/deck/select {deck_id} -> {success, deck_name}
export const selectDeck = (deckId) => request('POST', '/api/deck/select', { deck_id: deckId });

// ── 卡片流转 ──────────────────────────────────────────────
// GET /api/card/next -> {status:"card"|"waiting"|"finished", ...}
export const getNextCard = () => request('GET', '/api/card/next');

// GET /api/card/show -> {sentence, translation, keyword, answer_html}
export const getShow = () => request('GET', '/api/card/show');

// POST /api/card/answer {card_id, ease} -> 同 /api/card/next
export const answerCard = (cardId, ease) =>
    request('POST', '/api/card/answer', { card_id: cardId, ease });

// GET /api/card/sentence -> {ready:false} | {ready:true, sentence, translation, keyword}
export const getSentence = () => request('GET', '/api/card/sentence');

// POST /api/card/refresh_sentence -> 同 /api/card/next 卡片形状，或 {status:"error", error}
export const refreshSentence = () => request('POST', '/api/card/refresh_sentence');

// ── 撤回 ──────────────────────────────────────────────────
// GET /api/undo/status -> {can_undo, undo_name}
export const getUndoStatus = () => request('GET', '/api/undo/status');

// POST /api/undo -> 同 /api/card/next
export const undo = () => request('POST', '/api/undo');

// ── TTS / 媒体（返回 URL，由 <audio> / <img> 直接用）──────
export const ttsUrl = (text) => '/api/tts/' + encodeURIComponent(text);
export const mediaUrl = (p) => '/media/' + p;

// ── AI 流式对话（SSE over POST）──────────────────────────
// 调用方用 useSSE，这里只暴露底层 streamChat 不直接用。
export const AI_CHAT_URL = '/api/ai/chat';
