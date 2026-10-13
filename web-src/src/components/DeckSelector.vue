<template>
    <div id="deck-selector">
        <div class="deck-selector-header">
            <h2>选择牌组</h2>
            <!-- 与 AnkiWeb 云端同步（需桌面端已登录）-->
            <button class="btn-icon" :class="{ 'is-loading': syncing }" :disabled="syncing"
                    :title="syncing ? '同步中...' : '与 AnkiWeb 云端同步'" @click="$emit('sync')">
                <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">
                    <path d="M0 0h24v24H0z" fill="none"/>
                    <path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6c0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6c0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4l-4-4v3z"/>
                </svg>
            </button>
        </div>
        <div id="deck-list">
            <div v-if="loading" class="deck-item">加载中...</div>
            <div
                v-for="deck in decks"
                :key="deck.id"
                class="deck-item"
                @click="pick(deck)"
            >
                <div class="deck-item-name">{{ deck.name }}</div>
                <div class="deck-item-counts">
                    新: {{ deck.new_count }} | 学习: {{ deck.learning_count }} | 复习: {{ deck.review_count }}
                </div>
            </div>
        </div>
        <button class="btn-back" @click="$emit('back')">返回</button>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import * as api from '../api/client.js';

defineProps({
    syncing: { type: Boolean, default: false },
});
const emit = defineEmits(['select', 'back', 'sync']);
const decks = ref([]);
const loading = ref(true);

onMounted(async () => {
    try {
        decks.value = await api.getDecks();
    } catch (e) {
        decks.value = [];
    } finally {
        loading.value = false;
    }
});

function pick(deck) {
    emit('select', { id: deck.id, name: deck.name });
}
</script>
