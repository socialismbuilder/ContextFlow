<template>
    <div id="fab-container" ref="container">
        <div id="fab" ref="fab" class="fab"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" style="pointer-events:none"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="M10.487 10.503q.61-.612.61-1.503q0-.896-.61-1.506t-1.506-.61t-1.506.61T6.865 9q0 .89.61 1.503t1.506.613t1.506-.613m7.563 2.938q-.183-.074-.278-.244t-.022-.347q.356-.927.543-1.897T18.481 9t-.178-1.93q-.178-.949-.534-1.876q-.073-.177.025-.341t.281-.238q.214-.073.409.028t.274.315q.367.975.545 1.983T19.481 9q0 1.056-.19 2.084q-.191 1.028-.558 2.008q-.08.214-.274.317q-.195.104-.409.031m2.939 2.92q-.177-.08-.25-.24t.011-.331q.856-1.552 1.293-3.254q.438-1.702.438-3.485t-.44-3.487T20.725 2.3q-.084-.171-.009-.341t.253-.25q.214-.084.42.007q.207.092.317.286q.875 1.63 1.325 3.406t.45 3.63t-.444 3.63t-1.318 3.405q-.11.194-.323.283t-.407.003M3.558 18.5q-.039-.213-.173-.366t-.347-.153q-.232 0-.385.153q-.153.152-.134.366q.154 1.285 1.137 2.142t2.325.858q1.338 0 2.23-.756q.891-.755 1.397-2.14q.386-1.096.87-1.702t1.845-1.686q1.512-1.212 2.335-2.72T15.48 9q0-2.783-1.859-4.641T8.981 2.5q-2.667 0-4.497 1.695T2.519 8.5q-.019.214.134.357T3.019 9t.347-.143t.153-.357q.135-2.183 1.697-3.591T8.981 3.5q2.317 0 3.909 1.591Q14.48 6.683 14.48 9q0 1.777-.8 3.16q-.8 1.382-2.068 2.351q-1.185.893-1.824 1.687t-1.084 1.96q-.427 1.119-1.04 1.73t-1.683.612q-.883 0-1.576-.568T3.558 18.5"/></svg></div>
        <div id="fab-indicator" ref="indicator" class="fab-indicator hidden"></div>
    </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

const props = defineProps({
    answerVisible: { type: Boolean, default: false },
});
const emit = defineEmits(['answer', 'speak']);

const fab = ref(null);
const container = ref(null);
const indicator = ref(null);

// 方向：上=良好(3) 右=简单(4) 下=重来(1) 左=困难(2)
const DIRECTIONS = {
    up:    { label: '良好', ease: 3 },
    right: { label: '简单', ease: 4 },
    down:  { label: '重来', ease: 1 },
    left:  { label: '困难', ease: 2 },
};

let fabPos = { x: 0, y: 0 };
let isDragging = false;
let longPressTimer = null;
let isLongPress = false;
let startX = 0, startY = 0;
let dragOffsetX = 0, dragOffsetY = 0;
let currentDirection = null;

let dragArmed = false;
let lastTapTime = 0;
let lastTapX = 0, lastTapY = 0;
let speakTimer = null;
let dragArmTimer = null;
const DBL_TAP_GAP = 180;
const DBL_TAP_MOVE = 30;
const SPEAK_DELAY = 200;
const DRAG_ARM_TTL = 1000;

let mouseDown = false;
let volumeSvg = '';

// 答题按钮方向 SVG（用于滑动时替换 FAB 图标）
const dirSvg = {
    down:  '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="m5.927 18.192l1.735 1.735q.146.146.153.344q.006.198-.153.363q-.166.166-.357.169t-.357-.162l-2.382-2.383q-.131-.131-.184-.268q-.053-.136-.053-.298t.053-.298t.184-.267l2.382-2.383q.146-.146.347-.153t.367.159q.16.165.162.354t-.162.354l-1.735 1.734h10.765q.27 0 .443-.173t.173-.442v-2.885q0-.213.143-.356t.357-.144t.357.144t.143.356v2.885q0 .671-.472 1.143t-1.144.472zM18.073 6.808H7.308q-.27 0-.442.173q-.174.173-.174.442v2.885q0 .213-.143.357t-.357.143t-.356-.143t-.144-.357V7.423q0-.671.472-1.143t1.144-.472h10.765l-1.734-1.735q-.147-.146-.153-.344t.153-.363q.165-.166.356-.169q.192-.003.357.163l2.383 2.382q.13.131.183.268q.053.136.053.298t-.053.298q-.052.136-.183.267l-2.383 2.383q-.146.146-.347.153t-.366-.159q-.16-.165-.163-.354t.163-.354z"/></svg>',
    left:  '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="M4.126 20q-.234 0-.414-.111t-.28-.293q-.108-.179-.12-.387q-.01-.209.118-.421L11.3 5.212q.128-.212.308-.308T12 4.808t.391.096t.308.308l7.871 13.576q.128.212.115.417t-.118.391t-.282.295t-.41.109zm.324-1h15.1L12 6zm7.984-1.566q.182-.182.182-.434t-.182-.434t-.434-.181t-.434.181t-.182.434t.182.434t.434.181t.434-.181m-.077-2.193q.143-.144.143-.356v-4q0-.213-.144-.357t-.357-.143t-.356.143t-.143.357v4q0 .212.144.356t.357.144t.356-.144M12 12.5"/></svg>',
    up:    '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="m9.55 15.88l8.802-8.801q.146-.146.344-.156t.363.156t.166.357t-.165.356l-8.944 8.95q-.243.243-.566.243t-.566-.243l-4.05-4.05q-.146-.146-.152-.347t.158-.366t.357-.165t.357.165z"/></svg>',
    right: '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="m12 14.052l1.65 1.015q.217.137.444-.022q.227-.158.172-.426l-.443-1.886l1.47-1.264q.21-.186.12-.431q-.09-.246-.363-.27l-1.917-.176l-.76-1.761q-.106-.242-.373-.242t-.373.242l-.76 1.761l-1.917.175q-.273.025-.363.27t.12.432l1.47 1.264l-.442 1.886q-.056.268.17.426q.228.159.445.022zM9.073 19H6.616q-.672 0-1.144-.472T5 17.385v-2.458l-1.79-1.796q-.237-.243-.349-.538T2.75 12t.112-.593t.347-.538L5 9.073V6.616q0-.672.472-1.144T6.616 5h2.457l1.796-1.79q.243-.237.538-.349T12 2.75t.593.112t.538.347L14.927 5h2.458q.67 0 1.143.472q.472.472.472 1.144v2.457l1.79 1.796q.237.243.349.538t.111.593t-.111.593t-.348.538L19 14.927v2.458q0 .67-.472 1.143q-.472.472-1.143.472h-2.458l-1.796 1.79q-.243.237-.538.349T12 21.25t-.593-.111t-.538-.348zm.427-1l2.058 2.058q.173.173.442.173t.442-.173L14.5 18h2.885q.269 0 .442-.173t.173-.442V14.5l2.058-2.058q.173-.173.173-.442t-.173-.442L18 9.5V6.616q0-.27-.173-.443T17.385 6H14.5l-2.058-2.058Q12.27 3.77 12 3.77t-.442.173L9.5 6H6.616q-.27 0-.443.173T6 6.616V9.5l-2.058 2.058q-.173.173-.173.442t.173.442L6 14.5v2.885q0 .269.173.442t.443.173zm2.5-6"/></svg>',
};

function setFabPosition(x, y) {
    const maxX = window.innerWidth - 56;
    const maxY = window.innerHeight - 56;
    fabPos.x = Math.max(4, Math.min(maxX, x));
    fabPos.y = Math.max(4, Math.min(maxY, y));
    container.value.style.left = fabPos.x + 'px';
    container.value.style.top = fabPos.y + 'px';
    container.value.style.right = 'auto';
    container.value.style.bottom = 'auto';
}

function getDirection(dx, dy) {
    const angle = Math.atan2(dx, -dy) * 180 / Math.PI;
    if (angle >= -45 && angle < 45) return 'up';
    if (angle >= 45 && angle < 135) return 'right';
    if (angle >= 135 || angle < -135) return 'down';
    if (angle >= -135 && angle < -45) return 'left';
    return null;
}

function showDirection(dir) {
    if (currentDirection === dir) return;
    hideDirection();
    currentDirection = dir;
    if (dir && DIRECTIONS[dir] && dirSvg[dir]) {
        fab.value.innerHTML = dirSvg[dir];
        indicator.value.textContent = DIRECTIONS[dir].label;
        indicator.value.classList.remove('hidden');
    }
}
function hideDirection() {
    currentDirection = null;
    fab.value.innerHTML = volumeSvg;
    indicator.value.classList.add('hidden');
}

function handleTouchStart(e) {
    const touch = e.touches[0];
    startX = touch.clientX;
    startY = touch.clientY;
    isLongPress = false;
    isDragging = false;
    const rect = container.value.getBoundingClientRect();
    dragOffsetX = touch.clientX - rect.left;
    dragOffsetY = touch.clientY - rect.top;

    if (dragArmed) {
        dragArmed = false;
        fab.value.classList.remove('armed');
        if (dragArmTimer) { clearTimeout(dragArmTimer); dragArmTimer = null; }
        isDragging = true;
        fab.value.classList.add('dragging');
        return;
    }
    longPressTimer = setTimeout(() => {
        isLongPress = true;
        isDragging = true;
        fab.value.classList.add('dragging');
    }, 300);
}

function handleTouchMove(e) {
    e.preventDefault();
    const touch = e.touches[0];
    const dx = touch.clientX - startX;
    const dy = touch.clientY - startY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (!isLongPress && dist > 12) {
        clearTimeout(longPressTimer);
        longPressTimer = null;
        if (props.answerVisible) {
            if (dist > 20) showDirection(getDirection(dx, dy));
            else hideDirection();
        }
    }
    if (isDragging) setFabPosition(touch.clientX - dragOffsetX, touch.clientY - dragOffsetY);
}

function handleTouchEnd(e) {
    e.preventDefault();
    clearTimeout(longPressTimer);
    longPressTimer = null;
    fab.value.classList.remove('dragging');

    const touch = e.changedTouches[0];
    const dx = touch.clientX - startX;
    const dy = touch.clientY - startY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (isDragging) { isDragging = false; hideDirection(); lastTapTime = 0; return; }
    if (currentDirection && dist < 30) { hideDirection(); lastTapTime = 0; return; }
    if (currentDirection && props.answerVisible) {
        const action = DIRECTIONS[currentDirection];
        hideDirection();
        lastTapTime = 0;
        if (action) emit('answer', action.ease);
        return;
    }
    hideDirection();

    if (dist < 12) {
        const now = Date.now();
        const gap = now - lastTapTime;
        const movedFromLast = Math.hypot(touch.clientX - lastTapX, touch.clientY - lastTapY);
        const isSecondTap = gap < DBL_TAP_GAP && movedFromLast < DBL_TAP_MOVE && lastTapTime > 0;
        if (speakTimer) { clearTimeout(speakTimer); speakTimer = null; }
        if (isSecondTap) {
            lastTapTime = 0;
            dragArmed = true;
            fab.value.classList.add('armed');
            if (dragArmTimer) clearTimeout(dragArmTimer);
            dragArmTimer = setTimeout(() => {
                dragArmed = false; dragArmTimer = null;
                fab.value.classList.remove('armed');
            }, DRAG_ARM_TTL);
            return;
        }
        lastTapTime = now;
        lastTapX = touch.clientX;
        lastTapY = touch.clientY;
        speakTimer = setTimeout(() => {
            speakTimer = null;
            lastTapTime = 0;
            emit('speak');
        }, SPEAK_DELAY);
    }
}

// ── 鼠标（桌面调试）──
function onMouseDown(e) {
    mouseDown = true;
    startX = e.clientX;
    startY = e.clientY;
    isLongPress = false;
    isDragging = false;
    const rect = container.value.getBoundingClientRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;
    longPressTimer = setTimeout(() => {
        isLongPress = true; isDragging = true;
        fab.value.classList.add('dragging');
    }, 300);
}
function onMouseMove(e) {
    if (!mouseDown) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (!isLongPress && dist > 12) {
        clearTimeout(longPressTimer); longPressTimer = null;
        if (props.answerVisible) {
            if (dist > 20) showDirection(getDirection(dx, dy));
            else hideDirection();
        }
    }
    if (isDragging) setFabPosition(e.clientX - dragOffsetX, e.clientY - dragOffsetY);
}
function onMouseUp(e) {
    if (!mouseDown) return;
    mouseDown = false;
    clearTimeout(longPressTimer); longPressTimer = null;
    fab.value.classList.remove('dragging');
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (isDragging) { isDragging = false; hideDirection(); return; }
    if (currentDirection && dist < 30) { hideDirection(); return; }
    if (currentDirection && props.answerVisible) {
        const action = DIRECTIONS[currentDirection];
        hideDirection();
        if (action) emit('answer', action.ease);
        return;
    }
    hideDirection();
    if (dist < 12) emit('speak');
}

function onResize() {
    setFabPosition(
        Math.min(fabPos.x, window.innerWidth - 56),
        Math.min(fabPos.y, window.innerHeight - 56)
    );
}

onMounted(() => {
    volumeSvg = fab.value.innerHTML;
    fabPos = { x: window.innerWidth - 72, y: window.innerHeight - 140 };
    setFabPosition(fabPos.x, fabPos.y);

    fab.value.addEventListener('touchstart', handleTouchStart, { passive: true });
    fab.value.addEventListener('touchmove', handleTouchMove, { passive: false });
    fab.value.addEventListener('touchend', handleTouchEnd);
    fab.value.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });
    fab.value.addEventListener('mousedown', onMouseDown);

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    window.addEventListener('resize', onResize);
});

onUnmounted(() => {
    // 修复原代码隐患：彻底解绑所有监听器
    if (longPressTimer) clearTimeout(longPressTimer);
    if (speakTimer) clearTimeout(speakTimer);
    if (dragArmTimer) clearTimeout(dragArmTimer);
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    window.removeEventListener('resize', onResize);
});
</script>
