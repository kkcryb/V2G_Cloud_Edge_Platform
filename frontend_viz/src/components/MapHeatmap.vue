<template>
  <div class="component-wrapper">
    <div class="panel-header">
      <h3 class="panel-title">🌐 区域状态矩阵映射 (真实节点 ID)</h3>
      <div class="term-explanations">
        <span title="底层数据源于 adj.csv，此处将节点状态映射为电价或负荷压力。颜色偏红代表提价(抑制充电)，偏绿代表降价。">❓ 节点状态说明</span>
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
    tooltip: { trigger: 'item', formatter: '节点 ID: {b}<br/>状态参数: {c}' },
    visualMap: {
      type: 'continuous',
      calculable: true,
      inRange: { color: ['#00fa9a', '#1e90ff', '#ff4500'] }, // 绿->蓝->红
      text: ['高', '低'],
      textStyle: { color: '#ccc' },
      orient: 'horizontal', left: 'center', bottom: 10
    },
    series: [
      {
        type: 'graph',
        layout: 'circular', // 因为没有真实经纬度，采用标准环形布局展示 N 个节点
        roam: true,
        label: { show: false }, // 节点过多时隐藏文字，悬浮显示 Node ID
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(255, 255, 255, 0.2)' },
        data: []
      }
    ]
  };
  chartInstance.setOption(option);
  window.addEventListener('resize', () => chartInstance.resize());
});

// 严格绑定后端下发的状态矩阵 (不再凭空捏造数据)
watch(() => systemState.stations, (newStations) => {
  if (chartInstance && newStations && newStations.length > 0) {
    // 计算数据的最大最小值，以动态调整 VisualMap 区间
    const values = newStations.map(v => typeof v === 'object' ? v.value : v);
    const maxVal = Math.max(...values);
    const minVal = Math.min(...values);

    const realNodes = newStations.map((item, idx) => {
      // 兼容后端发来的是对象还是单一数值
      const val = typeof item === 'object' ? item.value : item;
      return {
        name: `Node_${idx}`, // 绝对不使用虚构城市名，使用真实索引 ID
        value: val.toFixed(3),
        symbolSize: 15 // 统一节点大小
      };
    });

    chartInstance.setOption({
      visualMap: { min: minVal, max: maxVal },
      series: [{ data: realNodes }]
    });
  }
}, { deep: true, immediate: true });
</script>

<style scoped>
.component-wrapper { display: flex; flex-direction: column; height: 100%; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
.panel-title { font-size: 1rem; color: #00fa9a; font-weight: 500; }
.term-explanations { font-size: 0.75rem; color: #888; }
.term-explanations span { cursor: help; border-bottom: 1px dotted #666; }
.echarts-container { flex: 1; }
</style>