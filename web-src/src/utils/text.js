// ── 纯文本工具 ───────────────────────────────────────────
// 取代原 app.js 的 escapeHtml / stripHtml / highlightHtml。

// 安全转义 HTML 文本（防 XSS）
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

// 去掉 HTML 标签得到纯文本（用于 TTS 朗读例句）
export function stripHtml(html) {
    const div = document.createElement('div');
    div.innerHTML = html || '';
    return (div.textContent || div.innerText || '').replace(/\s+/g, ' ').trim();
}

// 将 AI 例句中的 <u>...</u> 标记转换为高亮 span，其余文本安全转义。
// 受控解析：只有 <u> 标签保留为高亮，其余任何标签都按文本处理。
export function highlightHtml(text) {
    if (!text) return '';
    const parts = String(text).split(/(<u>.*?<\/u>)/);
    return parts.map(part => {
        const m = part.match(/^<u>(.*)<\/u>$/s);
        if (m) {
            return '<span class="highlight">' + escapeHtml(m[1]) + '</span>';
        }
        return escapeHtml(part);
    }).join('');
}
