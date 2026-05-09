<template>
  <div class="component-wrapper">
    <h3 class="panel-title">调度综合效能评估</h3>

    <div class="kpi-content">
      <!-- V2G 进度条 -->
      <div class="kpi-block">
        <div class="kpi-label">当前小时 V2G 任务完成度</div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" :style="{ width: systemState.v2gProgress + '%' }"></div>
        </div>
        <div class="kpi-value highlight">{{ systemState.v2gProgress.toFixed(1) }}%</div>
      </div>

      <!-- 纯 CSS 数字展示卡片 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-title">综合绿电消纳率</div>
          <div class="stat-num green">{{ systemState.greenEnergyRate.toFixed(2) }}%</div>
          <div class="stat-desc">目标: > 85%</div>
        </div>

        <div class="stat-card">
          <div class="stat-title">当前周期运行成本</div>
          <div class="stat-num blue">¥ {{ systemState.totalCost.toFixed(2) }}</div>
          <div class="stat-desc">包含电池损耗折旧</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { systemState } from '../store/wsStore';
</script>

<style scoped>
.component-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.panel-title {
  font-size: 1rem;
  color: var(--text-muted);
  margin-bottom: 20px;
  font-weight: normal;
}
.kpi-content {
  display: flex;
  flex-direction: column;
  gap: 30px;
  flex: 1;
}
.kpi-block {
  background: rgba(255,255,255,0.03);
  padding: 15px;
  border-radius: 8px;
}
.kpi-label {
  font-size: 0.9rem;
  margin-bottom: 10px;
}
.progress-bar-bg {
  width: 100%;
  height: 12px;
  background: #333;
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 10px;
}
.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #ff8c00, #ff4500);
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}
.kpi-value.highlight {
  font-size: 1.5rem;
  font-weight: bold;
  color: #ff4500;
  text-align: right;
}
.stats-grid {
  display: flex;
  gap: 15px;
}
.stat-card {
  flex: 1;
  background: rgba(255,255,255,0.03);
  padding: 15px;
  border-radius: 8px;
  text-align: center;
}
.stat-title {
  font-size: 0.85rem;
  color: #aaa;
  margin-bottom: 10px;
}
.stat-num {
  font-size: 1.8rem;
  font-weight: bold;
  margin-bottom: 5px;
}
.stat-num.green { color: var(--accent-green); }
.stat-num.blue { color: var(--accent-blue); }
.stat-desc {
  font-size: 0.75rem;
  color: #666;
}
</style>