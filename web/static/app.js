// ── ContextFlow Web 复习前端 ────────────────────────────

let currentCardId = null;
let currentActiveType = null;      // 当前卡片类型: new/learning/review
let currentCardMode = 'plain';     // 当前卡片模式: target / saved / plain
let waitTimer = null;
let sentencePollTimer = null;
let cachedOriginHtml = null;       // 缓存原始卡片背面 HTML
let cachedSentenceData = null;     // 缓存例句数据 {sentence, translation, keyword, mode}（背面时重渲染翻译）
let learningLanguage = '英语';      // 当前学习语言（决定 AI 选词分词规则），由 /api/status 提供

// ── 初始化 ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchNextCard();
    checkUndoStatus();
});

// ── 状态 ─────────────────────────────────────────────
async function fetchStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        document.getElementById('deck-name').textContent = data.deck_name || '未知牌组';
        if (data.learning_language) learningLanguage = data.learning_language;
        updateCounts(data.new || 0, data.learning || 0, data.review || 0, currentActiveType);
    } catch (e) {
        console.error('[ContextFlow] 获取状态失败:', e);
    }
}

function updateCounts(newCount, learningCount, reviewCount, activeType) {
    document.getElementById('count-new').textContent = newCount;
    document.getElementById('count-learning').textContent = learningCount;
    document.getElementById('count-review').textContent = reviewCount;

    // 高亮当前卡片对应的计数标签
    const types = ['new', 'learning', 'review'];
    types.forEach(t => {
        const el = document.getElementById('count-' + t);
        if (el) {
            el.classList.toggle('active', t === activeType);
        }
    });
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

    const mode = data.card_mode || 'plain';
    currentCardMode = mode;
    const isSentenceCard = (mode === 'target' || mode === 'saved');

    // 缓存背面数据，翻面时不再请求后端
    cachedOriginHtml = data.origin_html || null;
    cachedSentenceData = isSentenceCard
        ? { sentence: data.sentence, translation: data.translation, keyword: data.keyword, mode }
        : null;

    document.getElementById('origin-content').innerHTML = '';
    document.getElementById('card-css').innerHTML = '';

    if (isSentenceCard) {
        // target / saved：前端用数据渲染例句卡片
        renderSentenceCard(document.getElementById('contextflow-content'), {
            sentence: data.sentence,
            translation: data.translation,
            keyword: data.keyword,
            showTranslation: false,
            mode,
        });
        document.getElementById('contextflow-side').classList.remove('hidden');
        document.getElementById('origin-side').classList.add('hidden');
    } else {
        // plain：直接显示渲染好的原始卡片正面 HTML
        document.getElementById('contextflow-side').classList.add('hidden');
        document.getElementById('contextflow-content').innerHTML = '';
        document.getElementById('origin-side').classList.remove('hidden');
        document.getElementById('origin-content').innerHTML = data.question_html || '';
    }

    // 更新计数
    if (data.counts) {
        currentActiveType = data.active_type || null;
        updateCounts(data.counts.new, data.counts.learning, data.counts.review, currentActiveType);
    }

    // 更新按钮时间标签
    if (data.button_labels) {
        for (let i = 0; i < 4; i++) {
            const el = document.getElementById('btn-time-' + (i + 1));
            if (el) el.textContent = data.button_labels[i] || '';
        }
    }

    document.getElementById('answer-buttons').classList.add('hidden');
    document.getElementById('flip-btn').classList.remove('hidden');
    document.getElementById('flip-area').classList.remove('hidden');
    document.getElementById('card-area').classList.remove('hidden');

    playAutoAudio();

    // 自动点击朗读单词按钮（仅 target 牌组且有 keyword）
    if (mode === 'target' && data.keyword) {
        setTimeout(() => {
            const btn = document.getElementById('tts-word');
            if (btn && !btn.classList.contains('loading')) { btn.click(); }
        }, 300);
    }

    // target 牌组例句未就绪（例句生成中）→ 轮询
    if (mode === 'target' && data.sentence_ready === false) {
        startSentencePolling();
    } else {
        stopSentencePolling();
    }
}

// ── 显示背面 ───────────────────────────────────────
async function showAnswer() {
    if (!currentCardId) return;

    const mode = currentCardMode;
    const isSentenceCard = (mode === 'target' || mode === 'saved');

    document.getElementById('flip-btn').classList.add('hidden');
    document.getElementById('flip-area').classList.add('hidden');

    if (isSentenceCard) {
        // target / saved：重渲染例句卡片，显示真实翻译（遮挡条 → 翻译）
        if (cachedSentenceData) {
            renderSentenceCard(document.getElementById('contextflow-content'), {
                sentence: cachedSentenceData.sentence,
                translation: cachedSentenceData.translation,
                keyword: cachedSentenceData.keyword,
                showTranslation: true,
                mode: cachedSentenceData.mode,
            });
        }
    } else {
        // plain：隐藏例句区（origin_html 已包含完整背面）
        document.getElementById('contextflow-side').classList.add('hidden');
    }

    // 显示原始卡片背面：
    //   - target：原卡是用户的单词卡，背面是释义，与例句不重复 → 叠加显示
    //   - saved：原卡背面就是例句+翻译（Anki 模板渲染），与前端渲染重复 → 不显示
    //   - plain：整张卡都是原卡
    let showOriginSide = true;
    if (mode === 'saved') {
        showOriginSide = false;
        document.getElementById('origin-side').classList.add('hidden');
        document.getElementById('origin-content').innerHTML = '';
    } else if (cachedOriginHtml) {
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

    if (showOriginSide) {
        document.getElementById('origin-side').classList.remove('hidden');
    }
    document.getElementById('answer-buttons').classList.remove('hidden');

    // 自动点击朗读单词按钮（仅 target 牌组且有 keyword）
    if (mode === 'target' && cachedSentenceData && cachedSentenceData.keyword) {
        setTimeout(() => {
            const btn = document.getElementById('tts-word');
            if (btn && !btn.classList.contains('loading')) { btn.click(); }
        }, 300);
    }

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
        checkUndoStatus();
    } catch (e) {
        showError('答题失败', e.message);
    }
}

// ── 撤回 ──────────────────────────────────────────────
async function checkUndoStatus() {
    try {
        const resp = await fetch('/api/undo/status');
        const data = await resp.json();
        const btn = document.getElementById('undo-btn');
        if (btn) {
            btn.classList.toggle('hidden', !data.can_undo);
        }
    } catch (e) {
        console.error('[ContextFlow] 检查撤回状态失败:', e);
    }
}

async function undoCard() {
    showScreen('loading');
    try {
        const resp = await fetch('/api/undo', { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            showError('撤回失败', data.error);
            return;
        }
        currentCardId = data.card_id || null;
        fetchStatus();
        handleCardResponse(data);
        checkUndoStatus();
    } catch (e) {
        showError('撤回失败', e.message);
    }
}

// 键盘快捷键：u 撤回
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'u' || e.key === 'U') {
        e.preventDefault();
        const btn = document.getElementById('undo-btn');
        if (btn && !btn.classList.contains('hidden')) {
            undoCard();
        }
    }
});

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

// 去掉 HTML 标签，得到纯文本（用于 TTS 朗读例句）
function stripHtml(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    return (div.textContent || div.innerText || '').replace(/\s+/g, ' ').trim();
}

// 将 AI 例句中的 <u>...</u> 标记转换为高亮 span，其余文本安全转义（防 XSS）。
// 受控解析：只有 <u> 标签会被保留为高亮，其余任何标签都被当文本处理。
function highlightHtml(text) {
    if (!text) return '';
    // 用占位符分割出 <u>...</u> 片段
    const parts = text.split(/(<u>.*?<\/u>)/);
    return parts.map(part => {
        const m = part.match(/^<u>(.*)<\/u>$/s);
        if (m) {
            return '<span class="highlight">' + escapeHtml(m[1]) + '</span>';
        }
        return escapeHtml(part);
    }).join('');
}

// 构建例句卡片 DOM（target / saved 模式通用）。
//   showTranslation=false（正面）：例句 + 翻译遮挡条
//   showTranslation=true（背面）：例句 + 真实翻译
//   mode='target'：带朗读单词按钮 + 刷新按钮；mode='saved'：仅朗读例句按钮
const REFRESH_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">'
    + '<path d="M0 0h24v24H0z" fill="none"/>'
    + '<path fill="currentColor" d="M12.077 19q-2.931 0-4.966-2.033q-2.034-2.034-2.034-4.964t2.034-4.966T12.077 5q1.783 0 3.339.847q1.555.847 2.507 2.365V5.5q0-.213.144-.356T18.424 5t.356.144t.143.356v3.923q0 .343-.232.576t-.576.232h-3.923q-.212 0-.356-.144t-.144-.357t.144-.356t.356-.143h3.2q-.78-1.496-2.197-2.364Q13.78 6 12.077 6q-2.5 0-4.25 1.75T6.077 12t1.75 4.25t4.25 1.75q1.787 0 3.271-.968q1.485-.969 2.202-2.573q.085-.196.274-.275q.19-.08.388-.013q.211.067.28.275t-.015.404q-.833 1.885-2.56 3.017T12.077 19"/>'
    + '</svg>';

function renderSentenceCard(container, opts) {
    const { sentence, translation, keyword, showTranslation, mode } = opts;

    container.innerHTML = '';
    const root = document.createElement('div');
    root.className = 'cf-sentence-card';

    // 例句
    const sLabel = document.createElement('div');
    sLabel.className = 'label';
    sLabel.textContent = '例句';
    root.appendChild(sLabel);

    const sText = document.createElement('div');
    sText.className = 'card-text';
    sText.innerHTML = highlightHtml(sentence);
    root.appendChild(sText);

    // 翻译：正面用遮挡条，背面用真实翻译
    const tLabel = document.createElement('div');
    tLabel.className = 'label';
    tLabel.style.marginTop = '10px';
    tLabel.textContent = '翻译';
    root.appendChild(tLabel);

    const tText = document.createElement('div');
    tText.className = 'card-text';
    tText.style.lineHeight = '1.4';
    tText.style.opacity = '0.85';
    tText.style.fontSize = '14px';
    if (showTranslation) {
        tText.innerHTML = highlightHtml(translation);
    } else {
        tText.innerHTML =
            '<div class="translation-placeholder-line"></div>' +
            '<div class="translation-placeholder-line"></div>';
    }
    root.appendChild(tText);

    // 按钮组
    const btnGroup = document.createElement('div');
    btnGroup.className = 'tts-btn-group';

    // target 模式左侧放刷新按钮
    if (mode === 'target') {
        const refresh = document.createElement('div');
        refresh.className = 'tts-btn refresh-btn';
        refresh.id = 'refresh-btn';
        refresh.title = '重新生成例句';
        refresh.innerHTML = REFRESH_SVG;
        refresh.addEventListener('click', refreshSentence);
        btnGroup.appendChild(refresh);
    }

    const ttsRight = document.createElement('div');
    ttsRight.className = 'tts-right';

    // target 模式且有 keyword：朗读单词按钮
    if (mode === 'target' && keyword) {
        const wordBtn = document.createElement('div');
        wordBtn.className = 'tts-btn';
        wordBtn.id = 'tts-word';
        wordBtn.innerHTML = '<span class="tts-label">朗读单词</span>';
        wordBtn.addEventListener('click', () => {
            wordBtn.classList.add('loading');
            playTTS(keyword);
        });
        ttsRight.appendChild(wordBtn);
    }

    // 朗读例句按钮（target / saved 都有）
    const sentenceText = stripHtml(sentence);
    const sentBtn = document.createElement('div');
    sentBtn.className = 'tts-btn';
    sentBtn.id = 'tts-sentence';
    sentBtn.innerHTML = '<span class="tts-label">朗读例句</span>';
    sentBtn.addEventListener('click', () => {
        sentBtn.classList.add('loading');
        playTTS(sentenceText);
    });
    ttsRight.appendChild(sentBtn);

    // AI 解释入口（target / saved 都有）
    const aiBtn = document.createElement('div');
    aiBtn.className = 'tts-btn ai-explain-entry';
    aiBtn.innerHTML = '<span class="tts-label">AI 解释</span>';
    aiBtn.addEventListener('click', () => openAiSheet(sentenceText, keyword, mode));
    ttsRight.appendChild(aiBtn);

    btnGroup.appendChild(ttsRight);
    root.appendChild(btnGroup);

    container.appendChild(root);
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
        if (data.ready && data.sentence) {
            stopSentencePolling();
            // 缓存例句数据（翻面时直接使用，无需再请求后端）
            cachedSentenceData = {
                sentence: data.sentence,
                translation: data.translation,
                keyword: data.keyword,
                mode: 'target',
            };
            // 重渲染正面例句
            renderSentenceCard(document.getElementById('contextflow-content'), {
                sentence: data.sentence,
                translation: data.translation,
                keyword: data.keyword,
                showTranslation: false,
                mode: 'target',
            });
            // 轮询补上例句后自动朗读单词
            setTimeout(() => {
                const btn = document.getElementById('tts-word');
                if (btn && !btn.classList.contains('loading')) { btn.click(); }
            }, 300);
        }
    } catch (e) {
        console.error('[ContextFlow] sentence poll error:', e);
    }
}

// ── 重新生成例句（刷新）─────────────────────────────────
async function refreshSentence() {
    if (!currentCardId) return;
    stopSentencePolling();
    const startBtn = document.getElementById('refresh-btn');
    if (startBtn) startBtn.classList.add('spinning');
    try {
        const resp = await fetch('/api/card/refresh_sentence', { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            showError('刷新失败', data.error);
            return;
        }
        // 重新渲染当前卡片（可能命中缓存直接换句，也可能显示"例句生成中..."并启动轮询）
        // 渲染会替换 #refresh-btn 节点，所以旋转态在新节点上重新设置后由动画/轮询自然结束
        handleCardResponse(data);
    } catch (e) {
        showError('刷新失败', e.message);
    } finally {
        // 渲染后重新查找按钮，确保 spin 类在最新节点上移除
        setTimeout(() => {
            const b = document.getElementById('refresh-btn');
            if (b) b.classList.remove('spinning');
        }, 800);
    }
}

// ── 悬浮操作按钮（FAB）────────────────────────────────
(function() {
    const fab = document.getElementById('fab');
    const container = document.getElementById('fab-container');
    const indicator = document.getElementById('fab-indicator');

    if (!fab || !container) return;

    // 方向定义：角度 → 操作
    // 以正上方为0°，顺时针：上→简单，右→困难，下→重来，左→良好
    const DIRECTIONS = {
        up:    { label: '良好', ease: 3, cls: 'hint-up' },
        right: { label: '简单', ease: 4, cls: 'hint-right' },
        down:  { label: '重来', ease: 1, cls: 'hint-down' },
        left:  { label: '困难', ease: 2, cls: 'hint-left' },
    };

    // 保存位置
    let fabPos = { x: window.innerWidth - 72, y: window.innerHeight - 140 };
    let isDragging = false;
    let longPressTimer = null;
    let isLongPress = false;
    let startX = 0, startY = 0;
    let dragOffsetX = 0, dragOffsetY = 0;
    let currentDirection = null;

    // 双击进入拖动：快速点击两下后，下一次按下直接进入拖动
    let dragArmed = false;       // 是否已"装填"拖动（双击后置真，真正拖动后消耗）
    let lastTapTime = 0;         // 上一次轻触时间戳
    let lastTapX = 0, lastTapY = 0;
    let speakTimer = null;       // 单击朗读的延迟确认（等待是否双击）
    let dragArmTimer = null;     // 装填后的失效计时（1s 内未拖动则撤销）
    const DBL_TAP_GAP = 180;     // 双击最大间隔（ms）
    const DBL_TAP_MOVE = 30;     // 双击允许的位移（px）
    const SPEAK_DELAY = 200;     // 单击朗读延迟（须 > DBL_TAP_GAP，确保双击能取消朗读）
    const DRAG_ARM_TTL = 1000;   // 装填有效时长（ms）

    // 获取答题按钮的 SVG 图标用于滑动替换
    const btnSvgs = document.querySelectorAll('#answer-buttons .answer-btn svg');
    // down=重来(btn 0), left=困难(btn 1), up=良好(btn 2), right=简单(btn 3)
    const dirToBtnIdx = { down: 0, left: 1, up: 2, right: 3 };

    function setFabPosition(x, y) {
        const maxX = window.innerWidth - 56;
        const maxY = window.innerHeight - 56;
        fabPos.x = Math.max(4, Math.min(maxX, x));
        fabPos.y = Math.max(4, Math.min(maxY, y));
        container.style.left = fabPos.x + 'px';
        container.style.top = fabPos.y + 'px';
        container.style.right = 'auto';
        container.style.bottom = 'auto';
    }

    function getDirection(dx, dy) {
        // 计算角度（以正上方为0°，顺时针）
        const angle = Math.atan2(dx, -dy) * 180 / Math.PI;
        // angle: 上=0, 右=90, 下=±180, 左=-90
        if (angle >= -45 && angle < 45) return 'up';
        if (angle >= 45 && angle < 135) return 'right';
        if (angle >= 135 || angle < -135) return 'down';
        if (angle >= -135 && angle < -45) return 'left';
        return null;
    }

    // 保存音量 SVG 用于恢复
    const volumeSvg = fab.innerHTML;

    function showDirection(dir) {
        if (currentDirection === dir) return;
        hideDirection();
        currentDirection = dir;
        if (dir && DIRECTIONS[dir] && btnSvgs[dirToBtnIdx[dir]]) {
            fab.innerHTML = btnSvgs[dirToBtnIdx[dir]].outerHTML;
            indicator.textContent = DIRECTIONS[dir].label;
            indicator.classList.remove('hidden');
        }
    }

    function hideDirection() {
        currentDirection = null;
        fab.innerHTML = volumeSvg;
        indicator.classList.add('hidden');
    }

    function handleTouchStart(e) {
        const touch = e.touches[0];
        startX = touch.clientX;
        startY = touch.clientY;
        isLongPress = false;
        isDragging = false;

        const rect = container.getBoundingClientRect();
        dragOffsetX = touch.clientX - rect.left;
        dragOffsetY = touch.clientY - rect.top;

        // 双击已"装填"→ 本次按下直接进入拖动（消耗标志，不启长按计时）
        if (dragArmed) {
            dragArmed = false;
            fab.classList.remove('armed');
            if (dragArmTimer) { clearTimeout(dragArmTimer); dragArmTimer = null; }
            isDragging = true;
            fab.classList.add('dragging');
            return;
        }

        // 长按检测：300ms 后开始拖拽
        longPressTimer = setTimeout(() => {
            isLongPress = true;
            isDragging = true;
            fab.classList.add('dragging');
        }, 300);
    }

    function handleTouchMove(e) {
        e.preventDefault();
        const touch = e.touches[0];
        const dx = touch.clientX - startX;
        const dy = touch.clientY - startY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (!isLongPress && dist > 12) {
            // 移动超过阈值但未触发长按 → 取消长按计时，进入滑动模式
            clearTimeout(longPressTimer);
            longPressTimer = null;

            // 如果答题按钮可见，识别滑动方向
            if (isAnswerVisible()) {
                if (dist > 20) {
                    const dir = getDirection(dx, dy);
                    showDirection(dir);
                } else {
                    // 滑回中心附近，隐藏方向提示
                    hideDirection();
                }
            }
        }

        if (isDragging) {
            setFabPosition(
                touch.clientX - dragOffsetX,
                touch.clientY - dragOffsetY
            );
        }
    }

    function handleTouchEnd(e) {
        // 阻止浏览器在 touchend 后合成原生 click 事件（避免穿透到下层 tts-word 按钮触发朗读）
        e.preventDefault();
        clearTimeout(longPressTimer);
        longPressTimer = null;
        fab.classList.remove('dragging');

        const touch = e.changedTouches[0];
        const dx = touch.clientX - startX;
        const dy = touch.clientY - startY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (isDragging) {
            // 拖拽结束，仅移动位置
            isDragging = false;
            hideDirection();
            lastTapTime = 0; // 拖动后重置，避免与后续轻触误判双击
            return;
        }

        // 滑回中心区域（距离 < 30px）→ 取消操作，不触发答题
        if (currentDirection && dist < 30) {
            hideDirection();
            lastTapTime = 0;
            return;
        }

        if (currentDirection && isAnswerVisible()) {
            // 滑动方向确认 → 答题
            const action = DIRECTIONS[currentDirection];
            hideDirection();
            lastTapTime = 0;
            if (action) {
                answerCard(action.ease);
            }
            return;
        }

        hideDirection();

        // 纯轻触（无移动）→ 单击/双击判定
        if (dist < 12) {
            const now = Date.now();
            const gap = now - lastTapTime;
            const movedFromLast = Math.hypot(touch.clientX - lastTapX, touch.clientY - lastTapY);
            const isSecondTap = gap < DBL_TAP_GAP && movedFromLast < DBL_TAP_MOVE && lastTapTime > 0;

            // 任何轻触都先清掉挂起的延迟朗读（重置式：只保留"最后一次点击"的朗读意图）
            if (speakTimer) { clearTimeout(speakTimer); speakTimer = null; }

            if (isSecondTap) {
                // 构成双击 → 不再挂朗读，装填拖动
                lastTapTime = 0;
                dragArmed = true;
                fab.classList.add('armed'); // 装填态放大提示，与拖动样式一致
                // 1s 内未拖动则撤销装填
                if (dragArmTimer) clearTimeout(dragArmTimer);
                dragArmTimer = setTimeout(() => {
                    dragArmed = false;
                    dragArmTimer = null;
                    fab.classList.remove('armed');
                }, DRAG_ARM_TTL);
                return;
            }

            // 单击 → 记录 tap，延迟朗读；300ms 内再来一次则被上面清掉、转双击
            lastTapTime = now;
            lastTapX = touch.clientX;
            lastTapY = touch.clientY;
            speakTimer = setTimeout(() => {
                speakTimer = null;
                lastTapTime = 0; // 朗读确认，重置以等待下一次双击
                const btn = document.getElementById('tts-word');
                if (btn && !btn.classList.contains('loading')) {
                    btn.click();
                }
            }, SPEAK_DELAY);
        }
    }

    function isAnswerVisible() {
        const btns = document.getElementById('answer-buttons');
        return btns && !btns.classList.contains('hidden');
    }

    // 鼠标支持（桌面端调试）
    let mouseDown = false;
    fab.addEventListener('mousedown', (e) => {
        mouseDown = true;
        startX = e.clientX;
        startY = e.clientY;
        isLongPress = false;
        isDragging = false;
        const rect = container.getBoundingClientRect();
        dragOffsetX = e.clientX - rect.left;
        dragOffsetY = e.clientY - rect.top;
        longPressTimer = setTimeout(() => {
            isLongPress = true;
            isDragging = true;
            fab.classList.add('dragging');
        }, 300);
    });

    document.addEventListener('mousemove', (e) => {
        if (!mouseDown) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (!isLongPress && dist > 12) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
            if (isAnswerVisible()) {
                if (dist > 20) {
                    const dir = getDirection(dx, dy);
                    showDirection(dir);
                } else {
                    hideDirection();
                }
            }
        }

        if (isDragging) {
            setFabPosition(e.clientX - dragOffsetX, e.clientY - dragOffsetY);
        }
    });

    document.addEventListener('mouseup', (e) => {
        if (!mouseDown) return;
        mouseDown = false;
        clearTimeout(longPressTimer);
        longPressTimer = null;
        fab.classList.remove('dragging');

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (isDragging) {
            isDragging = false;
            hideDirection();
            return;
        }

        // 滑回中心区域（距离 < 30px）→ 取消操作
        if (currentDirection && dist < 30) {
            hideDirection();
            return;
        }

        if (currentDirection && isAnswerVisible()) {
            const action = DIRECTIONS[currentDirection];
            hideDirection();
            if (action) answerCard(action.ease);
            return;
        }

        hideDirection();

        if (dist < 12) {
            const btn = document.getElementById('tts-word');
            if (btn && !btn.classList.contains('loading')) btn.click();
        }
    });

    // 触摸事件
    fab.addEventListener('touchstart', handleTouchStart, { passive: true });
    fab.addEventListener('touchmove', handleTouchMove, { passive: false });
    fab.addEventListener('touchend', handleTouchEnd);
    // 兜底：吞掉 touchend 后浏览器合成的原生 click（穿透会触发下层 tts-word 朗读）
    fab.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });

    // 初始定位
    setFabPosition(fabPos.x, fabPos.y);

    // 窗口大小变化时调整位置
    window.addEventListener('resize', () => {
        setFabPosition(
            Math.min(fabPos.x, window.innerWidth - 56),
            Math.min(fabPos.y, window.innerHeight - 56)
        );
    });
})();

// ── AI 解释抽屉 ─────────────────────────────────────────
(function() {
    // 无空格语言：逐字分（汉语/日语/韩语等）。其余按空格+标点切。
    const NO_SPACE_LANGS = ['汉语', '中文', '日语', '韩语', '阿拉伯语'];

    // 状态
    let sheetSentence = '';        // 当前句子的纯文本
    let sheetKeyword = '';         // target 模式的关键词
    let sheetMode = 'plain';       // target / saved
    let aiMode = 'keyword';        // keyword（直接解释关键词）/ select（划词）
    let tokens = [];               // [{text}]
    let selStart = -1, selEnd = -1;
    let dragAnchor = -1;           // 划词按下时的起点 token 下标
    let didDrag = false;
    let history = [];              // 追问历史 [{role, content}]
    let streaming = false;
    let currentAiBubble = null;
    let currentAiRaw = '';

    const sheet = document.getElementById('ai-sheet');
    const backdrop = document.getElementById('ai-sheet-backdrop');
    const tokenArea = document.getElementById('ai-token-area');
    const modeBar = document.getElementById('ai-mode-bar');
    const selectedBar = document.getElementById('ai-selected-bar');
    const selectedText = document.getElementById('ai-selected-text');
    const explainBtn = document.getElementById('ai-explain-btn');
    const conversation = document.getElementById('ai-conversation');
    const inputEl = document.getElementById('ai-input');
    const sendBtn = document.getElementById('ai-send-btn');

    function isNoSpaceLang(lang) {
        return NO_SPACE_LANGS.some(l => (lang || '').includes(l));
    }

    function tokenize(text, language) {
        if (!text) return [];
        const arr = [];
        if (isNoSpaceLang(language)) {
            // 逐字，过滤空白
            for (const ch of [...text]) {
                if (/\s/.test(ch)) continue;
                arr.push({ text: ch });
            }
        } else {
            // 按空格切；每个 token 内可能附着前后标点（保留原样，便于显示与朗读）
            const parts = text.match(/\S+/g) || [];
            for (const p of parts) arr.push({ text: p });
        }
        return arr;
    }

    function renderTokens() {
        tokenArea.innerHTML = '';
        tokens.forEach((tok, i) => {
            const span = document.createElement('span');
            span.className = 'ai-token';
            span.textContent = tok.text;
            span.dataset.idx = i;
            if (i >= selStart && i <= selEnd && selStart >= 0) {
                span.classList.add('selected');
            }
            tokenArea.appendChild(span);
        });
    }

    function tokenIdxFromPoint(clientX, clientY) {
        const el = document.elementFromPoint(clientX, clientY);
        if (el && el.classList.contains('ai-token')) {
            return parseInt(el.dataset.idx, 10);
        }
        return -1;
    }

    // 从事件 target 取 token 下标（touchstart/mousedown 时 target 比 elementFromPoint 可靠，
    // 后者会被手指遮挡返回底层元素，导致单击选不中）
    function tokenIdxFromTarget(target) {
        if (target && target.classList && target.classList.contains('ai-token')) {
            return parseInt(target.dataset.idx, 10);
        }
        return -1;
    }

    function highlightRange(s, e) {
        const spans = tokenArea.querySelectorAll('.ai-token');
        spans.forEach(sp => {
            const i = parseInt(sp.dataset.idx, 10);
            sp.classList.toggle('selected', s >= 0 && i >= s && i <= e);
        });
    }

    function getSelectionText() {
        if (selStart < 0 || selEnd < 0) return '';
        return tokens.slice(selStart, selEnd + 1).map(t => t.text).join(
            isNoSpaceLang(learningLanguage) ? '' : ' '
        );
    }

    function updateSelectedBar() {
        const txt = getSelectionText();
        if (txt) {
            selectedText.textContent = txt;
            selectedBar.classList.remove('hidden');
            explainBtn.disabled = streaming;
        } else {
            selectedBar.classList.add('hidden');
        }
    }

    // ── 选词事件：单击与拖动分离 ──────────────────────
    // 单击选词用 click（target 永远可靠，不受手指遮挡影响）；
    // 拖动划词用 touchmove/mousemove，拖动发生时取消随后的 click（didDrag 标志）。

    function handleClick(e) {
        if (didDrag) { didDrag = false; return; } // 刚发生过拖动，吞掉这次 click
        const idx = tokenIdxFromTarget(e.target);
        if (idx < 0) return;
        // 单击：选中该 token（若在已选区间内则收缩到更长段）
        if (selStart >= 0 && idx >= selStart && idx <= selEnd) {
            const leftLen = idx - selStart;
            const rightLen = selEnd - idx;
            if (leftLen === 0 && rightLen === 0) {
                selStart = -1; selEnd = -1;
            } else if (leftLen >= rightLen) {
                selEnd = idx - 1;
            } else {
                selStart = idx + 1;
            }
        } else {
            selStart = idx;
            selEnd = idx;
        }
        highlightRange(selStart, selEnd);
        updateSelectedBar();
    }

    // 触屏拖动划词
    tokenArea.addEventListener('touchstart', (e) => {
        const idx = tokenIdxFromTarget(e.target);
        if (idx < 0) return;
        didDrag = false;
        dragAnchor = idx;
    }, { passive: true });
    tokenArea.addEventListener('touchmove', (e) => {
        if (dragAnchor < 0) return;
        e.preventDefault();
        const t = e.touches[0];
        const idx = tokenIdxFromPoint(t.clientX, t.clientY);
        if (idx < 0) return;
        didDrag = true;
        selStart = Math.min(dragAnchor, idx);
        selEnd = Math.max(dragAnchor, idx);
        highlightRange(selStart, selEnd);
    }, { passive: false });
    tokenArea.addEventListener('touchend', () => {
        if (didDrag) updateSelectedBar();
        // didDrag 保留，交给随之而来的 click 判定吞掉；click 后会重置
        dragAnchor = -1;
    });
    // click 处理单击（touchend 后浏览器会合成 click）
    tokenArea.addEventListener('click', handleClick);

    // 鼠标（桌面调试）：mousedown 起点 + mousemove 拖动 + mouseup/click 收尾
    tokenArea.addEventListener('mousedown', (e) => {
        const idx = tokenIdxFromTarget(e.target);
        if (idx < 0) return;
        didDrag = false;
        dragAnchor = idx;
    });
    document.addEventListener('mousemove', (e) => {
        if (dragAnchor < 0) return;
        const idx = tokenIdxFromPoint(e.clientX, e.clientY);
        if (idx < 0) return;
        if (idx !== dragAnchor) didDrag = true;
        selStart = Math.min(dragAnchor, idx);
        selEnd = Math.max(dragAnchor, idx);
        highlightRange(selStart, selEnd);
    });
    document.addEventListener('mouseup', () => {
        if (didDrag) updateSelectedBar();
        dragAnchor = -1;
        // mouseup 后浏览器也会触发 click，由 handleClick 统一处理单击 / 吞掉拖动
    });

    // ── 抽屉开关与模式 ──────────────────────────────────

    function setAiMode(mode) {
        aiMode = mode;
        modeBar.querySelectorAll('.ai-mode-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.mode === mode);
        });
        if (mode === 'keyword') {
            tokenArea.classList.add('hidden');
            selectedBar.classList.remove('hidden');
            selectedText.textContent = sheetKeyword || '(无关键词)';
            explainBtn.disabled = streaming || !sheetKeyword;
        } else {
            // select 划词模式
            tokenArea.classList.remove('hidden');
            updateSelectedBar();
        }
    }

    function openAiSheet(sentence, keyword, mode) {
        sheetSentence = sentence || '';
        sheetKeyword = keyword || '';
        sheetMode = mode || 'saved';
        tokens = tokenize(sheetSentence, learningLanguage);
        selStart = -1; selEnd = -1;
        history = [];
        streaming = false;
        currentAiBubble = null;
        currentAiRaw = '';
        conversation.innerHTML = '';
        inputEl.value = '';

        renderTokens();
        openAtMax(); // 打开时回到最大档高度

        // target 模式提供两种入口；saved 只能划词
        if (sheetMode === 'target' && sheetKeyword) {
            modeBar.classList.remove('hidden');
            setAiMode('keyword');   // 默认选中"解释关键词"，显示 keyword + 解释按钮，等用户点
            backdrop.classList.add('show');
            sheet.classList.add('open');
        } else {
            modeBar.classList.add('hidden');
            setAiMode('select');
            backdrop.classList.add('show');
            sheet.classList.add('open');
        }
    }

    function closeAiSheet() {
        sheet.classList.remove('open');
        backdrop.classList.remove('show');
        streaming = false; // 中断流式读取循环
    }
    backdrop.addEventListener('click', closeAiSheet);

    // ── 手柄拖动：顶端吸附 + 自由高度 ──────────────────
    // 拖动手柄改变抽屉高度（手柄的屏幕 y 即抽屉顶部位置）。
    // 松手时按高度判定：
    //   高度接近最大（≥ 最大-50）→ 吸附到最大
    //   高度低于半屏阈值          → 关闭
    //   其他                      → 保持当前高度（自由，不吸附）
    const handle = document.getElementById('ai-sheet-handle');
    const SNAP_RANGE = 50; // 距最大高度 50px 内吸附到最大
    let handleDragging = false;

    function maxSheetHeight() { return Math.round(window.innerHeight * 0.9); }
    function closeThreshold() { return Math.round(window.innerHeight * 0.5); }
    function clampHeight(h) {
        return Math.max(120, Math.min(maxSheetHeight(), h));
    }
    function setSheetHeight(h) { sheet.style.height = clampHeight(h) + 'px'; }
    function openAtMax() { setSheetHeight(maxSheetHeight()); }

    function handleDown() {
        handleDragging = true;
        sheet.style.transition = 'none'; // 拖动期间禁用过渡，跟随手指
    }
    function handleMove(clientY) {
        if (!handleDragging) return;
        setSheetHeight(window.innerHeight - clientY);
    }
    function handleUp() {
        if (!handleDragging) return;
        handleDragging = false;
        sheet.style.transition = ''; // 恢复过渡，做吸附/回弹动画
        const height = sheet.offsetHeight;
        if (height >= maxSheetHeight() - SNAP_RANGE) {
            // 接近最大高度 → 吸附到最大
            setSheetHeight(maxSheetHeight());
        } else if (height < closeThreshold()) {
            // 高度低于半屏 → 关闭
            closeAiSheet();
        }
        // 其他情况：保持当前高度（自由）
    }

    handle.addEventListener('touchstart', () => {
        handleDown();
    }, { passive: true });
    handle.addEventListener('touchmove', (e) => {
        if (!handleDragging) return;
        e.preventDefault();
        handleMove(e.touches[0].clientY);
    }, { passive: false });
    handle.addEventListener('touchend', handleUp);

    handle.addEventListener('mousedown', (e) => {
        handleDown();
        e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
        if (handleDragging) handleMove(e.clientY);
    });
    document.addEventListener('mouseup', () => {
        if (handleDragging) handleUp();
    });

    // 窗口尺寸变化时重新约束高度
    window.addEventListener('resize', () => {
        if (sheet.classList.contains('open')) {
            setSheetHeight(Math.min(sheet.offsetHeight, maxSheetHeight()));
        }
    });

    function aiExplainSelection() {
        if (streaming) return;
        const word = aiMode === 'keyword' ? sheetKeyword : getSelectionText();
        if (!word) return;
        // 点解释后，选词相关 UI 退场，只留对话区 + 输入栏
        modeBar.classList.add('hidden');
        tokenArea.classList.add('hidden');
        selectedBar.classList.add('hidden');
        startStream(word, '');
    }

    function aiSwitchMode(mode) { setAiMode(mode); }

    // ── SSE 流式对话 ────────────────────────────────────

    function addBubble(role, text) {
        const b = document.createElement('div');
        b.className = 'ai-bubble ' + (role === 'user' ? 'user' : 'ai');
        b.textContent = text;
        conversation.appendChild(b);
        conversation.scrollTop = conversation.scrollHeight;
        return b;
    }

    function renderAiBubble() {
        if (!currentAiBubble) return;
        let html = '';
        try {
            html = window.marked ? marked.parse(currentAiRaw) : escapeHtml(currentAiRaw);
        } catch (e) {
            html = escapeHtml(currentAiRaw);
        }
        currentAiBubble.innerHTML = html;
        conversation.scrollTop = conversation.scrollHeight;
    }

    function setStreaming(on) {
        streaming = on;
        sendBtn.disabled = on;
        // 解释按钮在流式期间一律禁用；结束后由 updateSelectedBar/setAiMode 重新决定
        explainBtn.disabled = on;
        inputEl.placeholder = on ? 'AI 生成中...' : '继续提问... (Enter发送, Shift+Enter换行)';
    }

    async function startStream(word, userFollowup) {
        if (streaming) return;
        if (userFollowup) {
            addBubble('user', userFollowup);
            history.push({ role: 'user', content: userFollowup });
        }

        // 创建 AI 气泡占位
        currentAiBubble = addBubble('ai', '');
        currentAiRaw = '';
        setStreaming(true);

        const body = {
            sentence: sheetSentence,
            word: word,
            history: history,
        };

        try {
            const resp = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!resp.ok) {
                const txt = await resp.text();
                showErrorBubble('请求失败 (' + resp.status + '): ' + txt.slice(0, 200));
                setStreaming(false);
                return;
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let fullContent = '';

            while (true) {
                if (!streaming) break; // 关闭抽屉时中断
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                // 按 SSE 事件边界 "\n\n" 拆分
                let idx;
                while ((idx = buffer.indexOf('\n\n')) >= 0) {
                    const rawEvent = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);
                    handleSseEvent(rawEvent, (delta) => {
                        currentAiRaw += delta;
                        fullContent += delta;
                        renderAiBubble();
                    });
                }
            }
            // 处理残余
            if (buffer.trim()) {
                handleSseEvent(buffer, (delta) => {
                    currentAiRaw += delta;
                    renderAiBubble();
                });
            }

            if (fullContent) {
                history.push({ role: 'assistant', content: fullContent });
            }
        } catch (e) {
            showErrorBubble('连接失败: ' + e.message);
        } finally {
            setStreaming(false);
            currentAiBubble = null;
            // 恢复解释按钮可用性
            if (aiMode === 'keyword') {
                explainBtn.disabled = !sheetKeyword;
            } else {
                explainBtn.disabled = !getSelectionText();
            }
        }
    }

    function handleSseEvent(rawEvent, onDelta) {
        // rawEvent 形如 "data: {...}"
        const lines = rawEvent.split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data:')) continue;
            const jsonStr = trimmed.slice(5).trim();
            if (!jsonStr || jsonStr === '[DONE]') return;
            try {
                const evt = JSON.parse(jsonStr);
                if (evt.type === 'delta' && evt.content) {
                    onDelta(evt.content);
                } else if (evt.type === 'error') {
                    showErrorBubble(evt.message || '未知错误');
                }
                // type === 'done' 无需处理
            } catch (e) { /* 忽略解析失败的事件 */ }
        }
    }

    function showErrorBubble(message) {
        if (currentAiBubble) {
            conversation.removeChild(currentAiBubble);
            currentAiBubble = null;
        }
        const b = document.createElement('div');
        b.className = 'ai-bubble error';
        b.textContent = message;
        conversation.appendChild(b);
        conversation.scrollTop = conversation.scrollHeight;
    }

    function aiSendFollowup() {
        const text = inputEl.value.trim();
        if (!text || streaming) return;
        inputEl.value = '';
        inputEl.style.height = 'auto';
        const word = aiMode === 'keyword' ? sheetKeyword : (getSelectionText() || sheetKeyword);
        startStream(word || text, text);
    }

    // 输入框：Enter 发送、自动增高
    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            aiSendFollowup();
        }
    });
    inputEl.addEventListener('input', () => {
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';
    });

    // 暴露给 onclick
    window.openAiSheet = openAiSheet;
    window.closeAiSheet = closeAiSheet;
    window.aiSwitchMode = aiSwitchMode;
    window.aiExplainSelection = aiExplainSelection;
    window.aiSendFollowup = aiSendFollowup;
})();
