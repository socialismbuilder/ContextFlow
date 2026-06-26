<template>
    <div class="screen">
        <div class="screen-icon">⏳</div>
        <h2>学习中卡片等待中</h2>
        <p class="wait-info">还有 <span>{{ remaining }}</span> 张学习中卡片</p>
        <p class="countdown">将在 <span class="countdown-num">{{ seconds }}</span> 秒后到达</p>
    </div>
</template>

<script setup>
defineProps({
    seconds: { type: Number, default: 0 },
    remaining: { type: Number, default: 0 },
});
</script>
