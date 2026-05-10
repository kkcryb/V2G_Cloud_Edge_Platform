<template>
  <div class="component-wrapper">
    <div class="panel-header">
      <h3 class="panel-title">实时物理滚动追踪</h3>
      <div class="status-box">
        <span class="dot online"></span> 边端集群同步中
      </div>
    </div>
    <div class="node-selector">
      <label>追踪节点：</label>
      <select v-model="selectedNodeId">
        <option value="ALL">全网总负荷聚合</option>
        <option v-for="i in 275" :key="i-1" :value="String(i-1)">Node {{ i-1 }}</option>
      </select>
    </div>
    <div ref="chartRef" class="echarts-container"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue';
import * as echarts from 'echarts';
import { systemState } from '../store/wsStore';

const chartRef = ref(null);
let chartInstance = null;
const selectedNodeId = ref('ALL');

onMounted(() => {
  chartInstance = echarts.init(chartRef.value);

  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['AI预测自然负荷 (基线)', '调控后物理执行负荷'],
      textStyle: { color: '#ccc' },
      top: '0%'
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: Array.from({length: 12}, (_, i) => `+${(i+1)*5}m`), // 12个5分钟步长
      axisLine: { lineStyle: { color: '#555' } },
      axisLabel: { color: '#aaa' }
    },
    yAxis: {
      type: 'value',
      name: '功率 (kW)',
      nameTextStyle: { color: '#888' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisLabel: { color: '#aaa' }
    },
    series: [
      {
        name: 'AI预测自然负荷 (基线)',
        type: 'line',
        smooth: true,
        lineStyle: { color: '#888', type: 'dashed', width: 2 },
        itemStyle: { color: '#888' },
        data: []
      },
      {
        name: '调控后物理执行负荷',
        type: 'line',
        smooth: true,
        lineStyle: { color: '#00fa9a', width: 3 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(0, 250, 154, 0.4)' },
            { offset: 1, color: 'rgba(0, 250, 154, 0.0)' }
          ])
        },
        itemStyle: { color: '#00fa9a' },
        data: []
      }
    ]
  };

  chartInstance.setOption(option);
  window.addEventListener('resize', () => chartInstance.resize());
});

watch([() => systemState.cloudBaselineCurve, () => systemState.actualCurve, selectedNodeId], ([baseline, actual]) => {
  if (chartInstance) {
    // 假设云端下发的数据存放在 systemState 中
    // 如果是单节点追踪，需要你在 run_system.py 中把单节点数据也推送到前端
    const baselineData = baseline || [];
    const actualData = actual ? actual.map(item => item[1]) : [];

    chartInstance.setOption({
      series: [
        { data: baselineData },
        { data: actualData }
      ]
    });
  }
}, { deep: true });
</script>

<style scoped>
.component-wrapper { display: flex; flex-direction: column; height: 100%; width: 100%; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.panel-title { margin: 0; font-size: 1.1rem; font-weight: 600; color: #00eaff; }
.status-box { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: #aaa; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.online { background: #00fa9a; box-shadow: 0 0 8px #00fa9a; }
.node-selector { margin-bottom: 15px; font-size: 0.9rem; color: #ccc; }
.node-selector select { background: #111; color: #fff; border: 1px solid #444; padding: 4px 8px; border-radius: 4px; outline: none; }
.echarts-container { flex: 1; min-height: 250px; }
</style>