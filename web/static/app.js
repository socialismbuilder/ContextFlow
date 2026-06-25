// ── ContextFlow Web 复习前端 ────────────────────────────

let currentCardId = null;
let currentActiveType = null;      // 当前卡片类型: new/learning/review
let currentCardMode = 'plain';     // 当前卡片模式: target / saved / plain
let waitTimer = null;
let sentencePollTimer = null;
let cachedOriginHtml = null;       // 缓存原始卡片背面 HTML
let cachedSentenceData = null;     // 缓存例句数据 {sentence, translation, keyword, mode}（背面时重渲染翻译）

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
