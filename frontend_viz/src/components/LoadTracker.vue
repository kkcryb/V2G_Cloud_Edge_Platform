<template>
  <div class="component-wrapper">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">
          5分钟级滚动追踪
          <span class="sub-title">（云端宏观规划 vs 边端微观执行）</span>
        </h3>
        <div class="term-explanations">
          <span title="GCN-LSTM预测得到的无控制自然负荷">AI预测基线</span> |
          <span title="云端VAE-WS-ADMM计算的未来1小时优化目标">运筹规划目标</span> |
          <span title="边缘节点每5分钟执行MQTT控制后的真实负荷">实际执行轨迹</span> |
          <span title="实际执行与目标轨迹之间的误差">Tracking Error</span>
        </div>
      </div>

      <div class="status-box">
        <div class="status-item">
          <span class="dot online"></span> 边端在线
        </div>
        <div class="status-item">
          当前步长：<strong>{{ currentStep }}</strong>
        </div>
        <div class="node-selector-wrapper">
          <label for="node-select">追踪维度：</label>
          <select id="node-select" v-model="selectedNodeId" @change="handleNodeChange">
            <option value="ALL">全网聚合总负荷</option>
            <option v-for="i in 275" :key="i-1" :value="String(i-1)">
              区域节点 [ID: {{ i-1 }}]
            </option>
          </select>
        </div>
      </div>
    </div>

    <div ref="chartRef" class="echarts-container"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue';
import * as echarts from 'echarts';
import { systemState } from '../store/wsStore';

const chartRef = ref(null);
let chartInstance = null;

const currentStep = ref(0);
const selectedNodeId = ref('ALL');
const singleNodeCurve = ref([]);
const N_AREAS = 275;

// 核心修复：深拷贝工具 (剥离 Vue Proxy 防止 ECharts 渲染失败)
const deepClone = (obj) => {
  if (!obj) return [];
  return JSON.parse(JSON.stringify(obj));
};

const formatToCoordinates = (arr = []) => {
  if (!Array.isArray(arr)) return [];
  if (Array.isArray(arr[0])) {
    return arr.filter(
      item => Array.isArray(item) && item.length >= 2 && Number.isFinite(item[0]) && Number.isFinite(item[1])
    );
  }
  return arr.filter(v => Number.isFinite(v)).map((val, idx) => [idx, val]);
};

const computeErrorArea = (actual, target) => {
  const result = [];
  const len = Math.min(actual.length, target.length);
  for (let i = 0; i < len; i++) {
    const actualY = actual[i][1];
    const targetY = target[i][1];
    if (Number.isFinite(actualY) && Number.isFinite(targetY)) {
      result.push([actual[i][0], actualY - targetY]);
    }
  }
  return result;
};

const handleNodeChange = () => {
  singleNodeCurve.value = [];
  if (chartInstance) {
    chartInstance.clear();
    initChart();
  }

  if (selectedNodeId.value !== 'ALL' && systemState.nodeDetails) {
    const pwr = systemState.nodeDetails[selectedNodeId.value] || 0;
    singleNodeCurve.value.push([currentStep.value, pwr]);
  }

  updateChart();
};

const initChart = () => {
  if (!chartRef.value) return;
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value);
  }

  const option = {
    backgroundColor: 'transparent',
    animation: true,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(20,20,20,0.92)',
      borderColor: '#444',
      textStyle: { color: '#eee' },
      formatter: params => {
        if (!params?.length) return '';
        const step = params[0].axisValue;
        let html = `<div style="margin-bottom:6px;"><strong>滚动步长：${step}</strong></div>`;
        let actual = null, target = null;

        params.forEach(item => {
          const value = item.data?.[1];
          html += `
            <div style="margin:3px 0;">
              <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${item.color};margin-right:6px;"></span>
              ${item.seriesName}：<strong>${Number(value).toFixed(2)} kW</strong>
            </div>`;
          if (item.seriesId === 'actual') actual = value;
          if (item.seriesId === 'target') target = value;
        });

        if (Number.isFinite(actual) && Number.isFinite(target)) {
          const error = actual - target;
          html += `
            <hr style="border-color:#333;" />
            <div>
              Tracking Error：
              <strong style="color:${Math.abs(error) > (selectedNodeId.value === 'ALL' ? 5 : 0.5) ? '#ff4500' : '#00fa9a'}">
                ${error.toFixed(2)} kW
              </strong>
            </div>`;
        }
        return html;
      }
    },
    legend: { top: 0, textStyle: { color: '#ccc' }, data: ['AI预测基线', '运筹规划目标', '实际执行轨迹', 'Tracking Error'] },
    grid: { left: '4%', right: '4%', bottom: '8%', top: '16%', containLabel: true },
    xAxis: { type: 'value', name: '5分钟步长', min: 0, max: value => Math.max(11, value.max), axisLine: { lineStyle: { color: '#666' } }, axisLabel: { color: '#aaa', formatter: val => `T${val}` }, splitLine: { lineStyle: { color: '#222' } } },
    yAxis: { type: 'value', scale: true, name: selectedNodeId.value === 'ALL' ? '全网聚合负荷 (kW)' : '单站负荷 (kW)', nameTextStyle: { color: '#aaa' }, axisLine: { lineStyle: { color: '#666' } }, axisLabel: { color: '#aaa' }, splitLine: { lineStyle: { color: '#333', type: 'dashed' } } },
    series: [
      { id: 'baseline', name: 'AI预测基线', type: 'line', smooth: true, showSymbol: false, z: 1, lineStyle: { color: '#777', width: 2, type: 'dashed' }, areaStyle: { color: 'rgba(120,120,120,0.06)' }, data: [] },
      { id: 'target', name: '运筹规划目标', type: 'line', smooth: true, showSymbol: false, z: 3, lineStyle: { color: '#00fa9a', width: 4 }, emphasis: { focus: 'series' }, data: [] },
      { id: 'actual', name: '实际执行轨迹', type: 'line', smooth: true, z: 5, showSymbol: true, symbol: 'circle', symbolSize: val => (val && val.length > 0 && val[0] === currentStep.value ? 10 : 5), lineStyle: { color: '#ff4500', width: 3 }, itemStyle: { color: '#ff4500' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(255,69,0,0.28)' }, { offset: 1, color: 'rgba(255,69,0,0)' }]) }, data: [] },
      { id: 'error', name: 'Tracking Error', type: 'bar', z: 0, barWidth: 10, itemStyle: { color: params => (Math.abs(params.value[1]) > (selectedNodeId.value === 'ALL' ? 5 : 0.5) ? '#ff4500' : '#00bfff'), opacity: 0.35 }, data: [] }
    ]
  };
  chartInstance.setOption(option);
};

const updateChart = () => {
  if (!chartInstance) return;

  const isAll = selectedNodeId.value === 'ALL';

  let baseline = formatToCoordinates(deepClone(systemState.baselineCurve));
  let target = formatToCoordinates(deepClone(systemState.cloudTargetCurve));
  let actual = [];

  if (isAll) {
    actual = formatToCoordinates(deepClone(systemState.actualLoadCurve));
  } else {
    baseline = baseline.map(pt => [pt[0], pt[1] / N_AREAS]);
    target = target.map(pt => [pt[0], pt[1] / N_AREAS]);
    actual = deepClone(singleNodeCurve.value);
  }

  const errorData = computeErrorArea(actual, target);

  chartInstance.setOption({
    yAxis: { name: isAll ? '全网聚合负荷 (kW)' : '单站实际负荷 (kW)' },
    series: [
      { id: 'baseline', data: baseline },
      { id: 'target', data: target },
      { id: 'actual', data: actual, showSymbol: actual.length <= 30 },
      { id: 'error', data: errorData }
    ]
  });
};

const handleResize = () => chartInstance?.resize();

onMounted(() => {
  initChart();
  updateChart();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  chartInstance?.dispose();
  chartInstance = null;
});

watch(
  () => systemState.actualLoadCurve,
  () => {
    const curve = deepClone(systemState.actualLoadCurve);

    if (!curve || curve.length === 0) {
      singleNodeCurve.value = [];
      currentStep.value = 0;
      updateChart();
      return;
    }

    const latestData = curve[curve.length - 1];
    const step = latestData[0];
    currentStep.value = step;

    if (selectedNodeId.value !== 'ALL' && systemState.nodeDetails) {
      const currentPower = systemState.nodeDetails[selectedNodeId.value] || 0;
      const lastSavedStep = singleNodeCurve.value.length > 0
        ? singleNodeCurve.value[singleNodeCurve.value.length - 1][0]
        : -1;

      if (step !== lastSavedStep) {
        singleNodeCurve.value.push([step, currentPower]);
      }
    }

    updateChart();
  },
  { deep: true }
);

watch(() => systemState.cloudTargetCurve, updateChart, { deep: true });
</script>

<style scoped>
.component-wrapper { display: flex; flex-direction: column; height: 100%; width: 100%; }
.panel-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.panel-title { margin: 0; font-size: 1rem; font-weight: 600; color: #00bfff; }
.sub-title { font-size: 0.82rem; color: #888; font-weight: 400; }
.term-explanations { margin-top: 4px; font-size: 0.74rem; color: #888; }
.term-explanations span { cursor: help; border-bottom: 1px dotted #555; transition: 0.2s; }
.term-explanations span:hover { color: #ddd; }
.status-box { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; font-size: 0.75rem; color: #aaa; }
.status-item { display: flex; align-items: center; gap: 6px; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.online { background: #00fa9a; box-shadow: 0 0 8px #00fa9a; }
.node-selector-wrapper { background: rgba(30, 30, 30, 0.8); border: 1px solid #444; padding: 4px 8px; border-radius: 4px; display: flex; align-items: center; }
.node-selector-wrapper label { color: #888; margin-right: 6px; }
.node-selector-wrapper select { background: transparent; color: #00bfff; border: none; font-size: 0.8rem; font-weight: bold; outline: none; cursor: pointer; }
.node-selector-wrapper select option { background: #222; color: #eee; }
.echarts-container { flex: 1; min-height: 300px; }
@media (max-width: 900px) { .panel-header { flex-direction: column; gap: 10px; } .status-box { align-items: flex-start; } }
</style>