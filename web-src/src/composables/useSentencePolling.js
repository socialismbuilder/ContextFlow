// ── 例句就绪轮询 ─────────────────────────────────────────
// target 模式下，后端可能尚未生成例句（sentence_ready=false），
// 每 2s 轮询 GET /api/card/sentence，直到 ready。
// 取代原 startSentencePolling / stopSentencePolling / pollSentence。

import * as api from '../api/client.js';

export function useSentencePolling() {
    let timer = null;

    function stop() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    // onReady(data) 在就绪时调用，data = {sentence, translation, keyword}
    function start(onReady) {
        stop();
        const poll = async () => {
            try {
                const data = await api.getSentence();
                if (data && data.ready && data.sentence) {
                    stop();
                    onReady(data);
                }
            } catch (e) {
                console.error('[ContextFlow] 例句轮询失败:', e);
            }
        };
        timer = setInterval(poll, 2000);
    }

    return { start, stop };
}
