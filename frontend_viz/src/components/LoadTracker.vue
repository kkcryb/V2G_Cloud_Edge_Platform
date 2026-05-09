<template>
  <div class="component-wrapper">
    <div class="panel-header">
      <h3 class="panel-title">📉 5分钟级滚动追踪 (云端宏观规划 vs 边端微观执行)</h3>
      <div class="term-explanations">
        <span title="时空图模型(GCN-LSTM)预测的无干预自然负荷">❓ 预测基线</span> |
        <span title="云端(VAE-WS-ADMM)计算得出的1小时最优控制目标">❓ 运筹目标</span> |
        <span title="边缘端每5分钟执行MQTT指令后的真实回传负荷">❓ 实际微观负荷</span>
      </div>
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

onMounted(() => {
  chartInstance = echarts.init(chartRef.value);

  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: {
      data: ['AI预测基线 (无干预)', '运筹规划目标 (云端下发)', '实际执行轨迹 (边端回传)'],
      textStyle: { color: '#ccc' }, top: 0
    },
    grid: { left: '3%', right: '3%', bottom: '8%', top: '15%', containLabel: true },
    xAxis: {
      type: 'value', min: 0, max: 11, // 对应1小时内12个5分钟步长
      axisLabel: { formatter: (val) => `步长 ${val}`, color: '#888' },
      splitLine: { show: true, lineStyle: { color: '#222' } }
    },
    yAxis: {
      type: 'value', name: '总负荷 (kW)',
      axisLabel: { color: '#888' },
      splitLine: { lineStyle: { color: '#333', type: 'dashed' } }
    },
    series: [
      {
        name: 'AI预测基线 (无干预)', type: 'line', smooth: true,
        lineStyle: { color: '#666', width: 2, type: 'dashed' },
        itemStyle: { color: '#666' }, showSymbol: false, data: []
      },
      {
        name: '运筹规划目标 (云端下发)', type: 'line', smooth: true,
        lineStyle: { color: '#00fa9a', width: 3 },
        itemStyle: { color: '#00fa9a' }, showSymbol: false, data: []
      },
      {
        name: '实际执行轨迹 (边端回传)', type: 'line', smooth: true,
        lineStyle: { color: '#ff4500', width: 2 },
        itemStyle: { color: '#ff4500' }, symbol: 'circle', symbolSize: 8,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(255, 69, 0, 0.3)' }, { offset: 1, color: 'rgba(255, 69, 0, 0)' }
          ])
        },
        data: []
      }
    ]
  };
  chartInstance.setOption(option);
  window.addEventListener('resize', () => chartInstance.resize());
});

// 监听真实状态流
watch(() => systemState.actualLoadCurve, (newVal) => {
  if (chartInstance) {
    // 【核心修复】：将后端的一维数组强制转化为 Echarts 需要的 [x, y] 二维坐标系
    const formatToCoordinates = (arr) => {
      if (!arr || arr.length === 0) return [];
      // 如果是一维数组 [50, 52...]，转为 [[0, 50], [1, 52]...]
      if (typeof arr[0] === 'number') {
        return arr.map((val, idx) => [idx, val]);
      }
      return arr;
    };

    chartInstance.setOption({
      series: [
        { data: formatToCoordinates(systemState.baselineCurve) },
        { data: formatToCoordinates(systemState.cloudTargetCurve) },
        { data: newVal } // actualLoadCurve 在 wsstore 里已经是 [step, load] 格式了
      ]
    });
  }
}, { deep: true });
</script>

<style scoped>
.component-wrapper { display: flex; flex-direction: column; height: 100%; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
.panel-title { font-size: 1rem; color: #00bfff; font-weight: 500; }
.term-explanations { font-size: 0.75rem; color: #888; }
.term-explanations span { cursor: help; border-bottom: 1px dotted #666; margin: 0 5px; }
.echarts-container { flex: 1; }
</style>