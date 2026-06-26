<template>
    <div id="card-area">
        <!-- ContextFlow 例句卡（target / saved）-->
        <SentenceCard
            v-if="isSentenceCard"
            ref="sentenceCardRef"
            :sentence="state.sentence"
            :translation="state.translation"
            :keyword="state.keyword"
            :show-translation="state.showAnswer"
            :mode="state.cardMode"
            :auto-read-word="state._autoReadWord"
            @refresh="$emit('refresh')"
            @open-ai="$emit('open-ai', $event)"
        />

        <!-- 原始卡片背面区域（plain 整张 / target 叠加释义 / saved 不显示）-->
        <div v-if="showOriginSide" id="origin-side">
            <div id="origin-content" class="card-content" v-html="originHtml"></div>
        </div>

        <!-- 翻面按钮（正面时）-->
        <div v-if="!state.showAnswer" id="flip-area" @click="$emit('flip')">
            <div id="flip-btn"><span>显示答案</span></div>
        </div>

        <!-- 答题按钮（背面时）-->
        <AnswerButtons v-if="state.showAnswer" :labels="state.buttonLabels" @answer="$emit('answer', $event)" />
    </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue';
import SentenceCard from './SentenceCard.vue';
import AnswerButtons from './AnswerButtons.vue';
import { playAutoAudio } from '../utils/tts.js';

const props = defineProps({
    state: { type: Object, required: true },
});
defineEmits(['flip', 'answer', 'refresh', 'open-ai']);

const sentenceCardRef = ref(null);

// 暴露朗读单词（供 App/FAB 调用）
defineExpose({
    clickWord: () => sentenceCardRef.value?.clickWord?.(),
});

const isSentenceCard = computed(
    () => props.state.cardMode === 'target' || props.state.cardMode === 'saved'
);

// plain：正面显示 questionHtml；背面显示 originHtml
// target：背面叠加 originHtml（释义）
// saved：不显示 origin-side（原卡背面就是例句，会重复）
const originHtml = computed(() => {
    if (props.state.cardMode === 'plain' && !props.state.showAnswer) {
        return props.state.questionHtml;
    }
    return props.state.originHtml;
});

const showOriginSide = computed(() => {
    if (props.state.cardMode === 'saved') return false;
    // plain 正面 / 任意模式背面，都显示原卡区域
    if (props.state.cardMode === 'plain') return true;
    return props.state.showAnswer;
});

// 卡片渲染后自动播放带 autoplay 的音频
watch(
    () => [props.state.showAnswer, props.state.sentence],
    () => nextTick(() => playAutoAudio(document.getElementById('card-area'))),
    { immediate: true }
);
</script>
