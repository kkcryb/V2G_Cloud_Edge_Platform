<template>
  <div class="chart-wrapper">
    <div ref="chartRef" class="echarts-container" style="height: 400px; width: 100%;"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue';
import * as echarts from 'echarts';
import { systemState } from '../store/wsStore';

const chartRef = ref(null);
let chartInstance = null;

onMounted(() => {
  chartInstance = echarts.init(chartRef.value, 'dark');

  const option = {
    title: { text: '云边协同负荷追踪实时仿真 (UrbanEV)', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    xAxis: { type: 'time', splitLine: { show: false } },
    yAxis: { type: 'value', name: '负荷 (kW)' },
    series: [
      {
        name: 'AI预测基线 (未干预)',
        type: 'line',
        itemStyle: { color: '#999' },
        lineStyle: { type: 'dotted', opacity: 0.5 },
        data: []
      },
      {
        name: '运筹优化目标 (1h规划)',
        type: 'line',
        itemStyle: { color: '#00fa9a' },
        lineStyle: { type: 'dashed', width: 2 },
        data: []
      },
      {
        name: '边缘实际执行 (5min滚动)',
        type: 'line',
        itemStyle: { color: '#ff4500' },
        lineStyle: { width: 3 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(255, 69, 0, 0.5)' },
            { offset: 1, color: 'rgba(255, 69, 0, 0.1)' }
          ])
        },
        data: []
      }
    ]
  };
  chartInstance.setOption(option);
});

// 监听状态，利用 ECharts 的 setOption 进行增量更新，形成平滑动效
watch(
  () => systemState.actualLoadCurve,
  (newVal) => {
    if (chartInstance) {
      chartInstance.setOption({
        series: [
          { data: systemState.baselineCurve },
          { data: systemState.cloudTargetCurve },
          { data: newVal }
        ]
      });
    }
  },
  { deep: true }
);
</script>