<template>
  <div class="dashboard-container">
    <div class="panel-left">
      <LoadTracker />
    </div>

    <div class="panel-center">
      <MapHeatmap />
    </div>

    <div class="panel-right">
      <KpiDashboard />
    </div>
  </div>
</template>

<script setup>
import LoadTracker from './components/LoadTracker.vue';
import MapHeatmap from './components/MapHeatmap.vue';
import KpiDashboard from './components/KpiDashboard.vue';
// 确保在 main.js 或此处初始化你的 WebSocket 监听
import { initWebSocket } from './store/wsstore.js';

onMounted(() => {
  console.log("正在初始化 WebSocket 连接...");
  initWebSocket(); // 启动连接！
});
</script>

<style>
/* 全局充斥科技感深色底色 */
body, html {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background-color: #050b14; /* 极深蓝底色 */
  color: #e0e0e0;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  overflow: hidden;
}

.dashboard-container {
  display: flex;
  width: 100vw;
  height: 100vh;
  box-sizing: border-box;
  padding: 15px;
  gap: 15px;
}

.panel-left, .panel-right {
  width: 25%;
  background: rgba(10, 20, 40, 0.7);
  border: 1px solid rgba(0, 234, 255, 0.2);
  box-shadow: 0 0 20px rgba(0, 234, 255, 0.05) inset;
  border-radius: 8px;
  padding: 15px;
  display: flex;
  flex-direction: column;
  z-index: 10;
}

.panel-center {
  width: 50%;
  position: relative;
  background: radial-gradient(circle at center, rgba(10, 20, 40, 0) 0%, rgba(5, 11, 20, 1) 100%);
  border-radius: 8px;
}
</style>