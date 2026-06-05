// ── ContextFlow Web 复习前端 ────────────────────────────

let currentCardId = null;
let waitTimer = null;
let sentencePollTimer = null;
let cachedOriginHtml = null;       // 缓存原始卡片背面 HTML
let cachedSentenceBackHtml = null; // 缓存例句+翻译 HTML（背面时替换 contextflow-content）

// ── 初始化 ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchNextCard();
});

// ── 状态 ─────────────────────────────────────────────
async function fetchStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        document.getElementById('deck-name').textContent = data.deck_name || '未知牌组';
        updateCounts(data.new || 0, data.learning || 0, data.review || 0);
    } catch (e) {
        console.error('[ContextFlow] 获取状态失败:', e);
    }
}

function updateCounts(newCount, learningCount, reviewCount) {
    document.getElementById('count-new').textContent = newCount;
    document.getElementById('count-learning').textContent = learningCount;
    document.getElementById('count-review').textContent = reviewCount;
}

// ── 获取下一张卡片 ───────────────────────────────────
async function fetchNextCard() {
    showScreen('loading');
    try {
        const resp = await fetch('/api/card/next');
        if (!resp.ok) {
            const text = await resp.text();
            console.error('[ContextFlow] API error:', resp.status, text);
            showError('API 错误 (' + resp.status + ')', text);
            return;
        }
        const data = await resp.json();
        handleCardResponse(data);
    } catch (e) {
        console.error('[ContextFlow] fetch error:', e);
        showError('连接失败', '无法连接到服务器，请确保 Anki 正在运行。\n' + e.message);
    }
}

function handleCardResponse(data) {
    if (data.status === 'card') {
        currentCardId = data.card_id;
        showQuestion(data);
    } else if (data.status === 'waiting') {
        showWaiting(data.wait_seconds, data.learning_remaining);
    } else if (data.status === 'finished') {
        showScreen('finished');
    } else if (data.error) {
        showError('API 错误', data.error);
    } else {
        showError('未知响应', JSON.stringify(data));
    }
}

// ── 显示正面 ───────────────────────────────────────
function showQuestion(data) {
    hideAllScreens();

    // 例句+隐藏条 → contextflow-content
    document.getElementById('contextflow-content').innerHTML = data.question_html || '';
    document.getElementById('origin-content').innerHTML = '';
    document.getElementById('card-css').innerHTML = '';

    // 缓存背面数据，翻面时不再请求后端
    cachedOriginHtml = data.origin_html || null;
    cachedSentenceBackHtml = data.sentence_back_html || null;

    // 更新计数
    if (data.counts) {
        updateCounts(data.counts.new, data.counts.learning, data.counts.review);
    }

    // 更新按钮时间标签
    if (data.button_labels) {
        for (let i = 0; i < 4; i++) {
            const el = document.getElementById('btn-time-' + (i + 1));
            if (el) el.textContent = data.button_labels[i] || '';
        }
    }

    // 显示例句区，隐藏原始卡片区和答题按钮
    document.getElementById('contextflow-side').classList.remove('hidden');
    document.getElementById('origin-side').classList.add('hidden');
    document.getElementById('answer-buttons').classList.add('hidden');
    document.getElementById('flip-btn').classList.remove('hidden');
    document.getElementById('card-area').classList.remove('hidden');

    playAutoAudio();

    // 自动点击朗读单词按钮
    setTimeout(() => {
        const btn = document.getElementById('tts-word');
        if (btn && !btn.classList.contains('loading')) { btn.click(); }
    }, 300);

    // 如果内容中有"例句生成中..."，启动轮询检查例句是否就绪
    if (data.question_html && data.question_html.includes('例句生成中')) {
        startSentencePolling();
    } else {
        stopSentencePolling();
    }
}

// ── 显示背面 ───────────────────────────────────────
async function showAnswer() {
    if (!currentCardId) return;

    document.getElementById('flip-btn').classList.add('hidden');

    // 用例句+翻译替换 contextflow-content 中的隐藏条
    if (cachedSentenceBackHtml) {
        document.getElementById('contextflow-content').innerHTML = cachedSentenceBackHtml;
    }

    // 显示原始卡片背面
    if (cachedOriginHtml) {
        document.getElementById('origin-content').innerHTML = cachedOriginHtml;
    } else {
        try {
            const resp = await fetch('/api/card/show');
            const data = await resp.json();
            document.getElementById('origin-content').innerHTML = data.answer_html || '';
        } catch (e) {
            showError('获取答案失败', e.message);
            return;
        }
    }

    document.getElementById('origin-side').classList.remove('hidden');
    document.getElementById('answer-buttons').classList.remove('hidden');

    // 自动点击朗读单词按钮
    setTimeout(() => {
        const btn = document.getElementById('tts-word');
        if (btn && !btn.classList.contains('loading')) { btn.click(); }
    }, 300);

    playAutoAudio();
}

// ── 答题 ─────────────────────────────────────────────
async function answerCard(ease) {
    if (!currentCardId) return;
    stopSentencePolling();

    try {
        const resp = await fetch('/api/card/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ card_id: currentCardId, ease: ease }),
        });
        const data = await resp.json();
        currentCardId = null;
        fetchStatus();
        handleCardResponse(data);
    } catch (e) {
        showError('答题失败', e.message);
    }
}

// ── 等待界面 ─────────────────────────────────────────
function showWaiting(seconds, remaining) {
    hideAllScreens();
    if (waitTimer) { clearInterval(waitTimer); waitTimer = null; }

    document.getElementById('learning-remaining').textContent = remaining;
    document.getElementById('wait-seconds').textContent = seconds;

    let remaining_sec = seconds;
    waitTimer = setInterval(() => {
        remaining_sec--;
        const el = document.getElementById('wait-seconds');
        if (el) el.textContent = Math.max(0, remaining_sec);
        if (remaining_sec <= 0) {
            clearInterval(waitTimer);
            waitTimer = null;
            fetchNextCard();
        }
    }, 1000);

    showScreen('waiting');
}

// ── 牌组选择 ─────────────────────────────────────────
async function showDeckSelector() {
    try {
        const resp = await fetch('/api/decks');
        const decks = await resp.json();
        renderDeckList(decks);
        document.getElementById('deck-selector').classList.remove('hidden');
    } catch (e) {
        showError('加载牌组失败', e.message);
    }
}

function hideDeckSelector() {
    document.getElementById('deck-selector').classList.add('hidden');
}

function renderDeckList(decks) {
    const list = document.getElementById('deck-list');
    list.innerHTML = '';
    decks.forEach(deck => {
        const item = document.createElement('div');
        item.className = 'deck-item';
        item.innerHTML = `
            <div class="deck-item-name">${escapeHtml(deck.name)}</div>
            <div class="deck-item-counts">
                新: ${deck.new_count} | 学习: ${deck.learning_count} | 复习: ${deck.review_count}
            </div>
        `;
        item.addEventListener('click', () => selectDeck(deck.id, deck.name));
        list.appendChild(item);
    });
}

async function selectDeck(deckId, deckName) {
    try {
        await fetch('/api/deck/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deck_id: deckId }),
        });
        document.getElementById('deck-name').textContent = deckName;
        hideDeckSelector();
        fetchNextCard();
    } catch (e) {
        showError('切换牌组失败', e.message);
    }
}

// ── 音频自动播放 ─────────────────────────────────────
function playAutoAudio() {
    document.querySelectorAll('.card-content audio[autoplay]').forEach(audio => {
        audio.play().catch(() => {});
    });
}

// ── 界面控制 ─────────────────────────────────────────
const screens = ['card-area', 'waiting-screen', 'finished-screen', 'loading-screen', 'error-screen'];

function hideAllScreens() {
    screens.forEach(id => document.getElementById(id).classList.add('hidden'));
}

function showScreen(name) {
    hideAllScreens();
    const el = document.getElementById(name + '-screen') || document.getElementById(name);
    if (el) el.classList.remove('hidden');
}

function showError(title, message) {
    hideAllScreens();
    document.getElementById('error-title').textContent = title;
    document.getElementById('error-message').textContent = message;
    document.getElementById('error-screen').classList.remove('hidden');
}

// ── 工具函数 ─────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── TTS 播放 ─────────────────────────────────────────
function playTTS(text) {
    if (!text) return;
    const audio = new Audio('/api/tts/' + encodeURIComponent(text));
    audio.play().catch(() => {});
    setTimeout(() => {
        document.querySelectorAll('.tts-btn.loading').forEach(btn => btn.classList.remove('loading'));
    }, 500);
}

// ── 例句轮询 ────────────────────────────────────────
function startSentencePolling() {
    stopSentencePolling();
    sentencePollTimer = setInterval(pollSentence, 2000);
}

function stopSentencePolling() {
    if (sentencePollTimer) {
        clearInterval(sentencePollTimer);
        sentencePollTimer = null;
    }
}

async function pollSentence() {
    try {
        const resp = await fetch('/api/card/sentence');
        const data = await resp.json();
        if (data.ready && data.question_html) {
            stopSentencePolling();
            document.getElementById('contextflow-content').innerHTML = data.question_html;
        }
    } catch (e) {
        console.error('[ContextFlow] sentence poll error:', e);
    }
}
