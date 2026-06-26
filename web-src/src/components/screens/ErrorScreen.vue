<template>
    <div class="screen">
        <div class="screen-icon">⚠️</div>
        <h2>{{ title }}</h2>
        <p style="white-space: pre-wrap; word-break: break-word;">{{ message }}</p>
        <button class="btn-primary" @click="$emit('retry')">重试</button>
    </div>
</template>

<script setup>
defineProps({
    title: { type: String, default: '出错了' },
    message: { type: String, default: '' },
});
defineEmits(['retry']);
</script>
