<template>
    <StatusBar
        :deck-name="state.deckName"
        :counts="state.counts"
        :active-type="state.activeType"
        :can-undo="state.canUndo"
        @select-deck="flow.openDeckSelector()"
        @undo="flow.undoCard()"
    />

    <!-- 卡片屏幕（状态条始终显示，卡片流转在内部切换）-->
    <CardArea v-if="state.screen === Screen.CARD" ref="cardAreaRef" :state="state" @flip="flow.showBack()" @answer="flow.answer($event)" @refresh="flow.refreshSentence()" @open-ai="openAi" />

    <!-- 牌组选择 -->
    <DeckSelector v-else-if="state.screen === Screen.DECK_SELECTOR" @select="onSelectDeck" @back="flow.closeDeckSelector()" />

    <!-- 静态屏 -->
    <WaitingScreen v-else-if="state.screen === Screen.WAITING" :seconds="state.waitSeconds" :remaining="state.learningRemaining" />
    <FinishedScreen v-else-if="state.screen === Screen.FINISHED" @continue="flow.fetchNext()" @select-deck="flow.openDeckSelector()" />
    <ErrorScreen v-else-if="state.screen === Screen.ERROR" :title="state.error.title" :message="state.error.message" @retry="flow.fetchNext()" />
    <LoadingScreen v-else />

    <!-- 悬浮答题按钮（仅卡片屏）-->
    <FabButton v-if="state.screen === Screen.CARD" :answer-visible="state.showAnswer" @answer="flow.answer($event)" @speak="cardAreaRef?.clickWord()" />

    <!-- AI 解释抽屉 -->
    <AiBottomSheet
        v-if="aiOpen"
        :sentence="aiSentence"
        :keyword="aiKeyword"
        :mode="aiMode"
        :language="state.learningLanguage"
        @close="aiOpen = false"
    />
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { useCardFlow, Screen } from './composables/useCardFlow.js';
import StatusBar from './components/StatusBar.vue';
import DeckSelector from './components/DeckSelector.vue';
import CardArea from './components/CardArea.vue';
import FabButton from './components/FabButton.vue';
import AiBottomSheet from './components/AiBottomSheet.vue';
import LoadingScreen from './components/screens/LoadingScreen.vue';
import WaitingScreen from './components/screens/WaitingScreen.vue';
import FinishedScreen from './components/screens/FinishedScreen.vue';
import ErrorScreen from './components/screens/ErrorScreen.vue';

const flow = useCardFlow();
const { state } = flow;

const cardAreaRef = ref(null);

// AI 抽屉状态
const aiOpen = ref(false);
const aiSentence = ref('');
const aiKeyword = ref('');
const aiMode = ref('saved');

function openAi({ sentence, keyword, mode }) {
    aiSentence.value = sentence;
    aiKeyword.value = keyword || '';
    aiMode.value = mode || 'saved';
    aiOpen.value = true;
}

function onSelectDeck({ id, name }) {
    flow.selectDeck(id, name);
}

// 全局键盘快捷键：u 撤回
function onKeydown(e) {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.key === 'u' || e.key === 'U') {
        e.preventDefault();
        if (state.canUndo) flow.undoCard();
    }
}
window.addEventListener('keydown', onKeydown);
onUnmounted(() => window.removeEventListener('keydown', onKeydown));

onMounted(() => flow.init());
</script>
