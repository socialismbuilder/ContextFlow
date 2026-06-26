// ── TTS 播放工具 ─────────────────────────────────────────
// 取代原 playTTS：GET /api/tts/<text> 返回 mp3，用 new Audio 播放。
// 点击按钮后会加 .loading 类，播放后 500ms 移除（保留原交互反馈）。

import { ttsUrl } from '../api/client.js';

export function playTTS(text, loadingEl) {
    const audio = new Audio(ttsUrl(text));
    if (loadingEl) loadingEl.classList.add('loading');
    audio.play().catch(() => {});
    if (loadingEl) {
        setTimeout(() => loadingEl.classList.remove('loading'), 500);
    }
}

// 自动播放卡片 HTML 中带 autoplay 的音频
export function playAutoAudio(root = document) {
    root.querySelectorAll('.card-content audio[autoplay]').forEach(audio => {
        audio.play().catch(() => {});
    });
}
