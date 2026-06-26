<template>
    <div id="contextflow-side">
        <div class="cf-sentence-card card-content">
            <div class="label">例句</div>
            <div class="card-text" v-html="highlightHtml(sentence)"></div>

            <div class="label" style="margin-top: 10px;">翻译</div>
            <div class="card-text">
                <template v-if="showTranslation">
                    <span v-html="highlightHtml(translation)"></span>
                </template>
                <template v-else>
                    <div class="translation-placeholder-line"></div>
                    <div class="translation-placeholder-line"></div>
                </template>
            </div>

            <div class="tts-btn-group">
                <div
                    v-if="mode === 'target'"
                    ref="refreshBtn"
                    class="tts-btn refresh-btn"
                    title="重新生成例句"
                    @click="$emit('refresh')"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">
                        <path d="M0 0h24v24H0z" fill="none"/>
                        <path fill="currentColor" d="M12.077 19q-2.931 0-4.966-2.033q-2.034-2.034-2.034-4.964t2.034-4.966T12.077 5q1.783 0 3.339.847q1.555.847 2.507 2.365V5.5q0-.213.144-.356T18.424 5t.356.144t.143.356v3.923q0 .343-.232.576t-.576.232h-3.923q-.212 0-.356-.144t-.144-.357t.144-.356t.356-.143h3.2q-.78-1.496-2.197-2.364Q13.78 6 12.077 6q-2.5 0-4.25 1.75T6.077 12t1.75 4.25t4.25 1.75q1.787 0 3.271-.968q1.485-.969 2.202-2.573q.085-.196.274-.275q.19-.08.388-.013q.211.067.28.275t-.015.404q-.833 1.885-2.56 3.017T12.077 19"/>
                    </svg>
                </div>
                <div class="tts-right">
                    <div
                        v-if="mode === 'target' && keyword"
                        ref="wordBtn"
                        class="tts-btn"
                        @click="readWord"
                    >
                        <span class="tts-label">朗读单词</span>
                    </div>
                    <div ref="sentenceBtn" class="tts-btn" @click="readSentence">
                        <span class="tts-label">朗读例句</span>
                    </div>
                    <div class="tts-btn ai-explain-entry" @click="$emit('open-ai', { sentence: plainSentence, keyword, mode })">
                        <span class="tts-label">AI 解释</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';
import { highlightHtml, stripHtml } from '../utils/text.js';
import { playTTS } from '../utils/tts.js';

const props = defineProps({
    sentence: { type: String, default: '' },
    translation: { type: String, default: '' },
    keyword: { type: String, default: '' },
    showTranslation: { type: Boolean, default: false },
    mode: { type: String, default: 'plain' },
    autoReadWord: { type: Boolean, default: false }, // App 触发自动朗读单词
});
const emit = defineEmits(['refresh', 'open-ai']);

const refreshBtn = ref(null);
const wordBtn = ref(null);
const sentenceBtn = ref(null);

// 纯文本例句（供 AI 抽屉用）
const plainSentence = stripHtml(props.sentence);

function readWord() {
    if (props.keyword) playTTS(props.keyword, wordBtn.value);
}
function readSentence() {
    playTTS(stripHtml(props.sentence), sentenceBtn.value);
}

// target 模式 + 有 keyword：正面渲染、翻面、轮询就绪后自动朗读单词（延迟 300ms）
// 对应原 showQuestion / showAnswer / pollSentence 三处的自动朗读
watch(
    () => [props.sentence, props.showTranslation, props.autoReadWord, props.keyword, props.mode],
    () => {
        if (props.mode === 'target' && props.keyword) {
            setTimeout(() => {
                if (wordBtn.value && !wordBtn.value.classList.contains('loading')) {
                    readWord();
                }
            }, 300);
        }
    },
    { immediate: true }
);

// 把 ref 暴露给父组件，供 FAB 双击朗读 / 等候轮询后朗读
defineExpose({
    clickWord: () => {
        if (wordBtn.value && !wordBtn.value.classList.contains('loading')) readWord();
    },
});
</script>
