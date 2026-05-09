<template>
  <div class="component-wrapper">
    <h3 class="panel-title">🎯 真实效能评估 (Real-time Metrics)</h3>

    <div class="kpi-content">
      <div class="stat-card">
        <div class="stat-title">当前周期 V2G 任务完成度</div>
        <div class="stat-num blue">{{ systemState.v2gProgress.toFixed(1) }}%</div>
        <div class="stat-desc">边缘集群实际放电量 / 云端宏观目标放电量</div>
      </div>

      <div class="stat-card">
        <div class="stat-title">动态微观偏差 (实时 MAE)</div>
        <div class="stat-num orange">{{ realTimeMAE }} kW</div>
        <div class="stat-desc">实际追踪负荷与云端目标的平均绝对误差</div>
      </div>

      <div class="stats-row">
        <div class="stat-sub-card">
          <div class="stat-title">绿电消纳率</div>
          <div class="stat-num green">{{ systemState.greenEnergyRate || 0 }}%</div>
        </div>
        <div class="stat-sub-card">
          <div class="stat-title">运行成本节约</div>
          <div class="stat-num green">¥ {{ systemState.totalCost || 0 }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { systemState } from '../store/wsStore';

// 【核心逻辑】：绝不捏造 MAE 误差数据，直接根据已发生的步数进行严格数学计算
const realTimeMAE = computed(() => {
  const actuals = systemState.actualLoadCurve;
  const targets = systemState.cloudTargetCurve;

  if (!actuals || actuals.length === 0 || !targets || targets.length === 0) return '0.00';

  let errorSum = 0;
  let count = 0;

  actuals.forEach(point => {
    const step = point[0];      // x轴的步长
    const actualLoad = point[1];// 真实负荷
    // 确保目标的索引存在
    if (targets[step] !== undefined) {
      const targetLoad = targets[step];
      errorSum += Math.abs(actualLoad - targetLoad);
      count++;
    }
  });

  return count > 0 ? (errorSum / count).toFixed(2) : '0.00';
});
</script>

<style scoped>
.component-wrapper { display: flex; flex-direction: column; height: 100%; }
.panel-title { font-size: 1rem; color: #ff8c00; margin-bottom: 15px; font-weight: 500; }
.kpi-content { display: flex; flex-direction: column; gap: 15px; flex: 1; }
.stat-card, .stat-sub-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 8px;
  padding: 15px;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
}
.stats-row { display: flex; gap: 15px; }
.stat-sub-card { flex: 1; padding: 10px; }
.stat-title { font-size: 0.85rem; color: #aaa; margin-bottom: 5px; }
.stat-desc { font-size: 0.7rem; color: #666; margin-top: 5px; text-align: center;}
.stat-num { font-size: 1.8rem; font-weight: bold; font-family: monospace; }
.stat-num.green { color: #00fa9a; }
.stat-num.orange { color: #ff8c00; }
.stat-num.blue { color: #1e90ff; }
</style>