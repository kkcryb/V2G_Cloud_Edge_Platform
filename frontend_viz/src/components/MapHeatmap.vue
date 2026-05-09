<template>
  <div class="chart-wrapper">
    <div ref="mapRef" class="echarts-container" style="height: 400px; width: 100%;"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue';
import * as echarts from 'echarts';
import { systemState } from '../store/wsStore';

const mapRef = ref(null);
let mapInstance = null;

onMounted(() => {
  mapInstance = echarts.init(mapRef.value, 'dark');

  const option = {
    title: { text: '充电站空间拓扑与动态电价热力图', left: 'center' },
    tooltip: { formatter: '{b}: 电价浮动 {c}%' },
    visualMap: {
      min: -20, max: 20, // 假设电价上下调区间为 -20% 到 +20%
      calculable: true,
      inRange: { color: ['#00fa9a', '#eede15', '#ff4500'] },
      text: ['高 (抑制充电)', '低 (鼓励充电)'],
      right: 10, bottom: 20
    },
    xAxis: { show: false }, // 隐藏虚拟坐标轴
    yAxis: { show: false },
    series: [{
      type: 'scatter',
      symbolSize: 20,
      data: []
    }]
  };
  mapInstance.setOption(option);
});

watch(
  () => systemState.stations,
  (newStations) => {
    // 假设 stations 格式: [{name: 'Station A', value: [经度, 纬度, 调价比例]}, ...]
    if (mapInstance) {
      mapInstance.setOption({
        series: [{ data: newStations }]
      });
    }
  },
  { deep: true }
);
</script>