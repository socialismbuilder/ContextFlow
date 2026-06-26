// ── 卡片流转状态机 ─────────────────────────────────────────
// 取代原 app.js 顶层的一组全局变量（currentCardId / currentCardMode /
// cachedOriginHtml / cachedSentenceData / waitTimer / learningLanguage …）
// 及 fetchStatus / fetchNextCard / handleCardResponse / showQuestion /
// showAnswer / answerCard / undo / checkUndo / showWaiting 等函数。
//
// 返回一个 reactive 状态对象 + 操作方法。App.vue 持有它，子组件通过
// props/inject 或事件回调与之交互。

import { reactive, ref } from 'vue';
import * as api from '../api/client.js';
import { useSentencePolling } from './useSentencePolling.js';

// 屏幕状态枚举
export const Screen = Object.freeze({
    LOADING: 'loading',
    CARD: 'card',
    WAITING: 'waiting',
    FINISHED: 'finished',
    ERROR: 'error',
    DECK_SELECTOR: 'deck-selector',
});

export function useCardFlow() {
    // ── 响应式状态 ──────────────────────────────────────
    const state = reactive({
        screen: Screen.LOADING,
        deckName: '加载中...',
        learningLanguage: '英语',
        counts: { new: 0, learning: 0, review: 0 },
        activeType: null,          // 'new' | 'learning' | 'review'
        canUndo: false,

        // 当前卡片
        cardMode: 'plain',         // 'target' | 'saved' | 'plain'
        showAnswer: false,         // 是否显示背面
        sentence: '',
        translation: '',
        keyword: '',
        sentenceReady: true,
        questionHtml: '',          // plain 模式正面
        originHtml: '',            // 原卡背面（plain/saved/target 叠加）
        buttonLabels: [],          // 四档按钮文案

        // 等待屏
        waitSeconds: 0,
        learningRemaining: 0,
        // 例句就绪后自动朗读单词标记
        _autoReadWord: false,

        error: { title: '', message: '' },
    });

    // ── 非响应式内部状态 ────────────────────────────────
    let currentCardId = null;
    let waitTimer = null;
    let cachedOriginHtml = null;   // 缓存原卡背面，翻面时不再请求后端
    let cachedSentenceData = null; // {sentence, translation, keyword, mode}，背面重渲染翻译用

    const polling = useSentencePolling();

    // ── 工具：填充卡片正面字段 ──────────────────────────
    function applyCard(data) {
        currentCardId = data.card_id;
        state._autoReadWord = false;
        const mode = data.card_mode || 'plain';
        const isSentenceCard = (mode === 'target' || mode === 'saved');

        // 缓存背面数据
        cachedOriginHtml = data.origin_html || null;
        cachedSentenceData = isSentenceCard
            ? { sentence: data.sentence, translation: data.translation, keyword: data.keyword, mode }
            : null;

        state.cardMode = mode;
        state.showAnswer = false;
        state.questionHtml = data.question_html || '';
        state.originHtml = '';
        state.sentence = data.sentence || '';
        state.translation = data.translation || '';
        state.keyword = data.keyword || '';
        state.sentenceReady = data.sentence_ready !== false;
        state.buttonLabels = data.button_labels || [];

        state.screen = Screen.CARD;

        // 计数
        if (data.counts) {
            state.activeType = data.active_type || null;
            state.counts = {
                new: data.counts.new || 0,
                learning: data.counts.learning || 0,
                review: data.counts.review || 0,
            };
        }

        // 例句未就绪 → 轮询
        if (mode === 'target' && data.sentence_ready === false) {
            polling.start(onSentenceReady);
        } else {
            polling.stop();
        }
    }

    // 轮询就绪回调：更新例句数据、自动朗读单词
    function onSentenceReady(data) {
        cachedSentenceData = {
            sentence: data.sentence,
            translation: data.translation,
            keyword: data.keyword,
            mode: state.cardMode,
        };
        state.sentence = data.sentence;
        state.translation = data.translation;
        state.keyword = data.keyword;
        state.sentenceReady = true;
        // App.vue / SentenceCard 负责触发自动朗读，这里仅置标记
        state._autoReadWord = true;
    }

    // ── 统一响应分发（原 handleCardResponse）────────────
    function handleResponse(data) {
        if (data.status === 'card') {
            applyCard(data);
        } else if (data.status === 'waiting') {
            showWaiting(data.wait_seconds, data.learning_remaining);
        } else if (data.status === 'finished') {
            polling.stop();
            state.screen = Screen.FINISHED;
        } else if (data.status === 'error' || data.error) {
            showError('API 错误', data.error || JSON.stringify(data));
        } else {
            showError('未知响应', JSON.stringify(data));
        }
    }

    function showWaiting(seconds, remaining) {
        if (waitTimer) { clearInterval(waitTimer); waitTimer = null; }
        state.waitSeconds = Math.max(0, seconds);
        state.learningRemaining = remaining;
        let remainingSec = seconds;
        waitTimer = setInterval(() => {
            remainingSec--;
            state.waitSeconds = Math.max(0, remainingSec);
            if (remainingSec <= 0) {
                clearInterval(waitTimer);
                waitTimer = null;
                fetchNext();
            }
        }, 1000);
        state.screen = Screen.WAITING;
    }

    function showError(title, message) {
        polling.stop();
        state.error = { title, message };
        state.screen = Screen.ERROR;
    }

    // ── 对外操作 ────────────────────────────────────────
    async function init() {
        await Promise.all([refreshStatus(), fetchNext(), checkUndo()]);
    }

    async function refreshStatus() {
        try {
            const data = await api.getStatus();
            state.deckName = data.deck_name || '未知牌组';
            if (data.learning_language) state.learningLanguage = data.learning_language;
            state.counts = {
                new: data.new || 0,
                learning: data.learning || 0,
                review: data.review || 0,
            };
        } catch (e) {
            console.error('[ContextFlow] 获取状态失败:', e);
        }
    }

    async function fetchNext() {
        state.screen = Screen.LOADING;
        try {
            const data = await api.getNextCard();
            handleResponse(data);
        } catch (e) {
            console.error('[ContextFlow] fetch error:', e);
            showError('连接失败', e.message);
        }
    }

    // 显示背面（原 showAnswer）
    async function showBack() {
        if (!currentCardId) return;
        const mode = state.cardMode;
        state.showAnswer = true;

        // 决定是否显示原卡背面
        //  - target：原卡是单词卡，背面释义与例句不重复 → 叠加
        //  - saved：原卡背面就是例句+翻译，与前端重复 → 不显示
        //  - plain：整张都是原卡
        if (mode === 'saved') {
            state.originHtml = '';
        } else if (cachedOriginHtml) {
            state.originHtml = cachedOriginHtml;
        } else {
            try {
                const data = await api.getShow();
                state.originHtml = data.answer_html || '';
            } catch (e) {
                showError('获取答案失败', e.message);
            }
        }
    }

    async function answer(ease) {
        if (!currentCardId) return;
        polling.stop();
        try {
            const data = await api.answerCard(currentCardId, ease);
            currentCardId = null;
            refreshStatus();
            handleResponse(data);
            checkUndo();
        } catch (e) {
            showError('答题失败', e.message);
        }
    }

    async function undoCard() {
        state.screen = Screen.LOADING;
        try {
            const data = await api.undo();
            if (data.error) {
                showError('撤回失败', data.error);
                return;
            }
            refreshStatus();
            handleResponse(data);
            checkUndo();
        } catch (e) {
            showError('撤回失败', e.message);
        }
    }

    async function checkUndo() {
        try {
            const data = await api.getUndoStatus();
            state.canUndo = !!data.can_undo;
        } catch (e) {
            console.error('[ContextFlow] 检查撤回状态失败:', e);
        }
    }

    // 切换牌组
    async function selectDeck(deckId, deckName) {
        try {
            await api.selectDeck(deckId);
            state.deckName = deckName;
            state.screen = Screen.CARD;
            fetchNext();
        } catch (e) {
            showError('切换牌组失败', e.message);
        }
    }

    // 刷新例句（供 SentenceCard 调用）
    async function refreshSentence() {
        if (!currentCardId) return;
        polling.stop();
        try {
            const data = await api.refreshSentence();
            if (data.status === 'error' || data.error) {
                showError('刷新失败', data.error || '未知错误');
                return;
            }
            handleResponse(data);
        } catch (e) {
            showError('刷新失败', e.message);
        }
    }

    function openDeckSelector() {
        polling.stop();
        state.screen = Screen.DECK_SELECTOR;
    }
    function closeDeckSelector() {
        state.screen = Screen.CARD;
    }

    return {
        state,
        Screen,
        polling,
        // 卡片流转
        init, refreshStatus, fetchNext, showBack, answer, undoCard, checkUndo,
        refreshSentence,
        // 牌组
        selectDeck, openDeckSelector, closeDeckSelector,
        // 直接暴露供组件读取的缓存
        getCachedSentence: () => cachedSentenceData,
    };
}
