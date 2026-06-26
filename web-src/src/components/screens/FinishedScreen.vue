<template>
    <div class="screen">
        <div class="screen-icon">🎉</div>
        <h2>今日复习完成！</h2>
        <button class="btn-primary" @click="$emit('continue')">继续检查</button>
        <button class="btn-secondary" @click="$emit('select-deck')">切换牌组</button>
    </div>
</template>

<script setup>
defineEmits(['continue', 'select-deck']);
</script>
