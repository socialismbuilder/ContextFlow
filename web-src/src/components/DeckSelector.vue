<template>
    <div id="deck-selector">
        <h2>选择牌组</h2>
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

const emit = defineEmits(['select', 'back']);
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
