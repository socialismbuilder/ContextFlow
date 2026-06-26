<template>
    <div id="status-bar">
        <div class="status-left">
            <!-- 切换牌组 -->
            <button class="btn-icon" title="切换牌组" @click="$emit('select-deck')">
                <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">
                    <path d="M0 0h24v24H0z" fill="none"/>
                    <path fill="currentColor" d="M4.5 17.27q-.213 0-.356-.145T4 16.768t.144-.356t.356-.143h15q.213 0 .356.144q.144.144.144.357t-.144.356t-.356.143zm0-4.77q-.213 0-.356-.144T4 11.999t.144-.356t.356-.143h15q.213 0 .356.144t.144.357t-.144.356t-.356.143zm0-4.77q-.213 0-.356-.143Q4 7.443 4 7.23t.144-.356t.356-.143h15q.213 0 .356.144T20 7.23t-.144.356t-.356.144z"/>
                </svg>
            </button>
            <!-- 撤回 -->
            <button v-if="canUndo" class="btn-icon" title="撤回 (U)" @click="$emit('undo')">
                <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">
                    <path d="M0 0h24v24H0z" fill="none"/>
                    <path fill="currentColor" d="M7.904 18q-.214 0-.357-.143t-.143-.357t.143-.357t.357-.143h6.754q1.556 0 2.65-1.067q1.096-1.067 1.096-2.606t-1.095-2.596q-1.096-1.058-2.651-1.058H6.916l2.611 2.611q.16.16.16.354t-.16.354t-.363.15q-.204-.01-.345-.15L5.565 9.74q-.13-.131-.183-.268q-.053-.136-.053-.298t.053-.298t.184-.267l3.253-3.254q.16-.16.354-.16t.354.16t.15.363t-.15.345l-2.611 2.61h7.742q1.963 0 3.355 1.354q1.39 1.354 1.39 3.3t-1.39 3.31T14.657 18z"/>
                </svg>
            </button>
            <span id="deck-name">{{ deckName }}</span>
        </div>
        <div id="counts">
            <span class="count new" :class="{ active: activeType === 'new' }">{{ counts.new }}</span>
            <span class="count learning" :class="{ active: activeType === 'learning' }">{{ counts.learning }}</span>
            <span class="count review" :class="{ active: activeType === 'review' }">{{ counts.review }}</span>
        </div>
    </div>
</template>

<script setup>
defineProps({
    deckName: { type: String, default: '' },
    counts: { type: Object, default: () => ({ new: 0, learning: 0, review: 0 }) },
    activeType: { type: String, default: null },
    canUndo: { type: Boolean, default: false },
});
defineEmits(['select-deck', 'undo']);
</script>
