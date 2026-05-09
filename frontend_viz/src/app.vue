<template>
  <div class="dashboard-root">
    <header class="header">
      <h1>云边协同 V2G 控制平台</h1>
      <div class="status-indicator">
        数据链路状态:
        <span :class="systemState.isConnected ? 'online' : 'offline'">
          {{ systemState.isConnected ? '仿真运行中' : '等待连接...' }}
        </span>
      </div>
    </header>

    <main class="grid-container">
      <div class="top-row">
        <!-- 空间维度与 KPI -->
        <MapHeatmap class="grid-item"/>
        <KpiDashboard class="grid-item"/>
      </div>
      <div class="bottom-row">
        <!-- 时间维度闭环追踪 -->
        <LoadTracker class="grid-item full-width"/>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { systemState, initWebSocket } from './store/wsStore';
import MapHeatmap from './components/MapHeatmap.vue';
import LoadTracker from './components/LoadTracker.vue';
import KpiDashboard from './components/KpiDashboard.vue'; // KPI 组件结构类似，展示 progress 和 cost

onMounted(() => {
  // 组件挂载即发起 WebSocket 连接，实现“一键运行”的数据贯通
  initWebSocket('ws://127.0.0.1:8000/ws/dashboard');
});
</script>

<style>
/* 简单的深色网格布局体系 */
.dashboard-root {
  background-color: #101014;
  color: #fff;
  min-height: 100vh;
  padding: 20px;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #333;
  padding-bottom: 10px;
  margin-bottom: 20px;
}
.status-indicator span { font-weight: bold; }
.online { color: #00fa9a; }
.offline { color: #ff4500; }
.grid-container { display: flex; flex-direction: column; gap: 20px; }
.top-row { display: flex; gap: 20px; }
.grid-item { flex: 1; background: #1a1a24; border-radius: 8px; padding: 15px; }
.full-width { flex: 100%; }
</style>