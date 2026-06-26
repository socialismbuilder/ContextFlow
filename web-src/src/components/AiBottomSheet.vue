<template>
    <div>
        <!-- 背景 -->
        <div id="ai-sheet-backdrop" class="show" @click="close"></div>

        <!-- 抽屉 -->
        <div id="ai-sheet" ref="sheet" class="ai-sheet open">
            <div class="ai-sheet-handle" ref="handle" @click="onHandleClick">
                <svg class="ai-handle-bar" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 24" preserveAspectRatio="none"><path d="M0 0h36v24H0z" fill="none"/><path fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" d="M4 8 L18 18 L32 8"/></svg>
            </div>

            <!-- 模式栏（target+keyword 双模式）-->
            <div v-if="showModeBar && !explained" id="ai-mode-bar" class="ai-mode-bar">
                <button class="ai-mode-btn" :class="{ active: aiMode === 'keyword' }" @click="setMode('keyword')">解释关键词</button>
                <button class="ai-mode-btn" :class="{ active: aiMode === 'select' }" @click="setMode('select')">划词选择</button>
            </div>

            <!-- 选词区（select 模式）-->
            <div
                v-show="aiMode === 'select' && !explained"
                id="ai-token-area"
                ref="tokenArea"
                class="ai-token-area"
                @click="onClickToken"
                @touchstart.passive="onTokenTouchStart"
                @touchmove.prevent="onTokenTouchMove"
                @touchend="onTokenTouchEnd"
                @mousedown="onTokenMouseDown"
            >
                <span
                    v-for="(tok, i) in tokens"
                    :key="i"
                    class="ai-token"
                    :class="{ selected: isSelected(i) }"
                    :data-idx="i"
                >{{ tok.text }}</span>
            </div>

            <!-- 选中条 -->
            <div v-if="showSelectedBar && !explained" id="ai-selected-bar" class="ai-selected-bar">
                <span class="ai-selected-label">选中：</span>
                <span id="ai-selected-text" class="ai-selected-text">{{ selectedText }}</span>
                <button id="ai-explain-btn" class="ai-explain-btn" :disabled="streaming || !hasWord" @click="explain">解释</button>
            </div>

            <!-- 对话区 -->
            <div id="ai-conversation" ref="conversation" class="ai-conversation">
                <div
                    v-for="(b, i) in bubbles"
                    :key="i"
                    class="ai-bubble"
                    :class="b.role"
                    v-html="b.html"
                ></div>
            </div>

            <!-- 输入栏 -->
            <div class="ai-input-bar">
                <textarea
                    ref="inputEl"
                    id="ai-input"
                    class="ai-input"
                    rows="1"
                    :placeholder="streaming ? 'AI 生成中...' : '继续提问... (Enter发送, Shift+Enter换行)'"
                    @keydown="onInputKeydown"
                    @input="autoGrow"
                ></textarea>
                <button id="ai-send-btn" class="ai-send-btn" :disabled="streaming" @click="sendFollowup">发送</button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { streamChat } from '../composables/useSSE.js';
import { escapeHtml } from '../utils/text.js';

const props = defineProps({
    sentence: { type: String, default: '' },
    keyword: { type: String, default: '' },
    mode: { type: String, default: 'saved' },
    language: { type: String, default: '英语' },
});
const emit = defineEmits(['close']);

const sheet = ref(null);
const handle = ref(null);
const tokenArea = ref(null);
const conversation = ref(null);
const inputEl = ref(null);

const aiMode = ref('keyword');      // 'keyword' | 'select'
const tokens = ref([]);
const selStart = ref(-1);
const selEnd = ref(-1);
const bubbles = ref([]);            // [{role:'user'|'ai'|'error', html}]
const streaming = ref(false);
const explained = ref(false);       // 已进入纯对话态：隐藏模式栏/选词区/选中条
const history = [];

let dragAnchor = -1;
let didDrag = false;
let currentBubbleIdx = -1;          // 当前流式 bubble 在 bubbles 中的下标
let currentAiRaw = '';
let abortController = null;

// 是否展示模式栏：target + 有 keyword 才有 keyword/select 切换；否则只 select
const showModeBar = computed(() => props.mode === 'target' && !!props.keyword);

// 单个字符是否为 CJK（中日韩统一表意/扩展A、假名、韩文、全角符号）
const CJK_RE = /[㐀-鿿豈-﫿぀-ヿ가-힯＀-￯]/;
function isCjkChar(ch) {
    return ch ? CJK_RE.test(ch) : false;
}

// 文本驱动分词（不依赖语言名字符串，避免语言名误判导致英文被逐字拆开）：
//   - CJK 字符逐字
//   - 英文等：连续字母/数字为一个词（保留撇号、连字符，如 don't / state-of-the-art）
//   - 标点符号独立成一个 token
const TOKEN_RE = /[㐀-鿿豈-﫿぀-ヿ가-힯＀-￯]|[A-Za-z0-9À-ɏЀ-ӿ][A-Za-z0-9À-ɏЀ-ӿ''-]*|[^\s]/g;
function tokenize(text) {
    if (!text) return [];
    const arr = [];
    TOKEN_RE.lastIndex = 0;
    let m;
    while ((m = TOKEN_RE.exec(text)) !== null) {
        arr.push({ text: m[0] });
    }
    return arr;
}

function isSelected(i) {
    return selStart.value >= 0 && i >= selStart.value && i <= selEnd.value;
}

const selectedText = computed(() => {
    // keyword 模式：显示关键词（与 explain() 取值一致）
    if (aiMode.value === 'keyword') return props.keyword || '';
    if (selStart.value < 0 || selEnd.value < 0) return '';
    const slice = tokens.value.slice(selStart.value, selEnd.value + 1);
    // 选中片段若含 CJK 字符则不加空格连接（逐字本就紧挨），英文则用空格连接
    const joiner = slice.some(t => isCjkChar(t.text)) ? '' : ' ';
    return slice.map(t => t.text).join(joiner);
});

const hasWord = computed(() =>
    aiMode.value === 'keyword' ? !!props.keyword : !!selectedText.value
);

// 选中条：keyword 模式常显（显示 keyword）；select 模式仅在有选中时显示
const showSelectedBar = computed(() => {
    if (streaming.value) return false;
    if (aiMode.value === 'keyword') return !!props.keyword;
    return !!selectedText.value;
});

// ── 模式切换 ──────────────────────────────────────────
function setMode(mode) {
    aiMode.value = mode;
    if (mode === 'keyword') {
        selStart.value = -1;
        selEnd.value = -1;
    }
}

// ── 选词交互 ──────────────────────────────────────────
function tokenIdxFromTarget(target) {
    if (target && target.classList && target.classList.contains('ai-token')) {
        return parseInt(target.dataset.idx, 10);
    }
    return -1;
}
function tokenIdxFromPoint(x, y) {
    const el = document.elementFromPoint(x, y);
    if (el && el.classList.contains('ai-token')) {
        return parseInt(el.dataset.idx, 10);
    }
    return -1;
}

// 单击选词
function onClickToken(e) {
    if (didDrag) { didDrag = false; return; }
    const idx = tokenIdxFromTarget(e.target);
    if (idx < 0) return;
    if (selStart.value >= 0 && idx >= selStart.value && idx <= selEnd.value) {
        const leftLen = idx - selStart.value;
        const rightLen = selEnd.value - idx;
        if (leftLen === 0 && rightLen === 0) {
            selStart.value = -1; selEnd.value = -1;
        } else if (leftLen >= rightLen) {
            selEnd.value = idx - 1;
        } else {
            selStart.value = idx + 1;
        }
    } else {
        selStart.value = idx;
        selEnd.value = idx;
    }
}

function onTokenTouchStart(e) {
    const idx = tokenIdxFromTarget(e.target);
    if (idx < 0) return;
    didDrag = false;
    dragAnchor = idx;
}
function onTokenTouchMove(e) {
    if (dragAnchor < 0) return;
    const t = e.touches[0];
    const idx = tokenIdxFromPoint(t.clientX, t.clientY);
    if (idx < 0) return;
    didDrag = true;
    selStart.value = Math.min(dragAnchor, idx);
    selEnd.value = Math.max(dragAnchor, idx);
}
function onTokenTouchEnd() {
    dragAnchor = -1;
}
function onTokenMouseDown(e) {
    const idx = tokenIdxFromTarget(e.target);
    if (idx < 0) return;
    didDrag = false;
    dragAnchor = idx;
}

// document 鼠标拖动（桌面调试）
function onDocMouseMove(e) {
    if (dragAnchor < 0) return;
    const idx = tokenIdxFromPoint(e.clientX, e.clientY);
    if (idx < 0) return;
    if (idx !== dragAnchor) didDrag = true;
    selStart.value = Math.min(dragAnchor, idx);
    selEnd.value = Math.max(dragAnchor, idx);
}
function onDocMouseUp() {
    dragAnchor = -1;
}

// ── 手柄拖拽：向下滑一点即关闭（不调高度）──────────────
// 抽屉高度固定为 90vh，拖动手柄时抽屉实时跟随手指下移（仅视觉位移），
// 松手时：下拖超过阈值 → 关闭；否则回弹回原位。
let handleDragging = false;
let handleStartY = 0;       // 按下时的 clientY
let handleOffsetY = 0;      // 当前下移位移（>=0）
let didDragHandle = false;  // 本次是否发生过拖动（用来吞掉 touchend 后合成的 click）

const CLOSE_DRAG_PX = 60;   // 下拖超过 60px 即关闭

function openAtFixed() {
    // 高度由 CSS 的 top/bottom 控制（移动 webview 下 vh 不可靠，故不在 JS 里设 height）
    if (!sheet.value) return;
    sheet.value.style.transform = '';
}

function handleDown(clientY) {
    handleDragging = true;
    didDragHandle = false;
    handleStartY = clientY;
    handleOffsetY = 0;
    sheet.value.style.transition = 'none';
}
function handleMove(clientY) {
    if (!handleDragging) return;
    // 只允许向下跟随（向上位移为 0）
    handleOffsetY = Math.max(0, clientY - handleStartY);
    if (handleOffsetY > 0) didDragHandle = true;
    sheet.value.style.transform = `translateY(${handleOffsetY}px)`;
}
function handleUp() {
    if (!handleDragging) return;
    handleDragging = false;
    sheet.value.style.transition = ''; // 恢复过渡，回弹/下滑有动画
    if (handleOffsetY >= CLOSE_DRAG_PX) {
        close();
    } else {
        sheet.value.style.transform = '';
    }
    handleOffsetY = 0;
}

// 点击手柄（未拖动时）= 关闭抽屉
function onHandleClick() {
    if (didDragHandle) { didDragHandle = false; return; } // 吞掉拖动后合成的 click
    close();
}

function onHandleTouchStart(e) { handleDown(e.touches[0].clientY); }
function onHandleTouchMove(e) {
    if (!handleDragging) return;
    e.preventDefault();
    handleMove(e.touches[0].clientY);
}
function onHandleTouchEnd() { handleUp(); }
function onHandleMouseDown(e) { handleDown(e.clientY); e.preventDefault(); }

function onDocHandleMove(e) { handleMove(e.clientY); }
function onDocHandleUp() { handleUp(); }

function onResize() {
    // 高度固定为 90vh（由 CSS vh 自适应），无需手动约束
}

// ── 流式对话 ──────────────────────────────────────────
function renderMarkdown() {
    if (currentBubbleIdx < 0) return;
    let html;
    try {
        html = window.marked ? window.marked.parse(currentAiRaw) : escapeHtml(currentAiRaw);
    } catch {
        html = escapeHtml(currentAiRaw);
    }
    bubbles.value[currentBubbleIdx].html = html;
    nextTick(() => {
        if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight;
    });
}

function showErrorBubble(message) {
    // 移除当前流式占位气泡（若有）
    if (currentBubbleIdx >= 0) {
        bubbles.value.splice(currentBubbleIdx, 1);
        currentBubbleIdx = -1;
    }
    bubbles.value.push({ role: 'error', html: escapeHtml(message) });
    nextTick(() => {
        if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight;
    });
}

function explain() {
    if (streaming.value) return;
    const word = aiMode.value === 'keyword' ? props.keyword : selectedText.value;
    if (!word) return;
    // 首次解释：模式栏/选词区/选中条退场，只留对话区 + 输入栏
    if (bubbles.value.length === 0) explained.value = true;
    startStream(word, '');
}

async function startStream(word, userFollowup) {
    if (streaming.value) return;
    if (userFollowup) {
        bubbles.value.push({ role: 'user', html: escapeHtml(userFollowup) });
        history.push({ role: 'user', content: userFollowup });
    }
    // AI 占位气泡
    currentAiRaw = '';
    bubbles.value.push({ role: 'ai', html: '' });
    currentBubbleIdx = bubbles.value.length - 1;
    streaming.value = true;

    abortController = new AbortController();
    let fullContent = '';
    await streamChat(
        { sentence: props.sentence, word, history },
        {
            onDelta: (delta) => {
                currentAiRaw += delta;
                fullContent += delta;
                renderMarkdown();
            },
            onError: (msg) => {
                showErrorBubble(msg);
            },
        },
        abortController.signal
    );

    streaming.value = false;
    currentBubbleIdx = -1;
    abortController = null;
    if (fullContent) {
        history.push({ role: 'assistant', content: fullContent });
    }
}

function sendFollowup() {
    const text = inputEl.value.value.trim();
    if (!text || streaming.value) return;
    inputEl.value.value = '';
    inputEl.value.style.height = 'auto';
    const word = aiMode.value === 'keyword' ? props.keyword : (selectedText.value || props.keyword);
    startStream(word || text, text);
}

function onInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendFollowup();
    }
}
function autoGrow() {
    const el = inputEl.value;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
}

function close() {
    if (abortController) abortController.abort();
    // 先下滑收起，动画结束后再通知父组件销毁
    if (sheet.value) {
        sheet.value.style.transform = 'translateY(100%)';
        setTimeout(() => emit('close'), 280);
    } else {
        emit('close');
    }
}

onMounted(() => {
    // 初始化 tokens + 默认模式
    tokens.value = tokenize(props.sentence);
    aiMode.value = (props.mode === 'target' && props.keyword) ? 'keyword' : 'select';
    openAtFixed();

    // document 级监听（onUnmounted 解绑，修复原代码隐患）
    document.addEventListener('mousemove', onDocMouseMove);
    document.addEventListener('mouseup', onDocMouseUp);
    document.addEventListener('mousemove', onDocHandleMove);
    document.addEventListener('mouseup', onDocHandleUp);
    window.addEventListener('resize', onResize);

    handle.value.addEventListener('touchstart', onHandleTouchStart, { passive: true });
    handle.value.addEventListener('touchmove', onHandleTouchMove, { passive: false });
    handle.value.addEventListener('touchend', onHandleTouchEnd);
    handle.value.addEventListener('mousedown', onHandleMouseDown);
});

onUnmounted(() => {
    document.removeEventListener('mousemove', onDocMouseMove);
    document.removeEventListener('mouseup', onDocMouseUp);
    document.removeEventListener('mousemove', onDocHandleMove);
    document.removeEventListener('mouseup', onDocHandleUp);
    window.removeEventListener('resize', onResize);
});
</script>
