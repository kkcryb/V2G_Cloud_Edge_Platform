<template>
  <div class="component-wrapper">
    <div class="panel-header">
      <h3 class="panel-title">🌐 深圳市 UrbanEV 节点调控映射</h3>
    </div>
    <div ref="chartRef" class="echarts-container"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue';
import * as echarts from 'echarts';
import { systemState } from '../store/wsStore';

// 🚨 引入真实的地图与坐标数据 (请确保你的文件路径与命名和下面一致)
import shenzhenGeoJson from '../assets/shenzhen.json';
import geoCoordMap from '../assets/node_coordinates.json';

const chartRef = ref(null);
let chartInstance = null;

onMounted(() => {
  chartInstance = echarts.init(chartRef.value);

  // 1. 核心：向 Echarts 注册深圳地图底图数据
  echarts.registerMap('shenzhen', shenzhenGeoJson);

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: function (params) {
        return `节点: <b>Node ${params.name}</b><br/>云端调价系数: ${params.value[2].toFixed(3)}`;
      }
    },
    // 2. 添加视觉映射组件：根据第三个维度的值(调价系数)自动赋予红黄绿颜色
    visualMap: {
      min: -0.2, // 根据你算法下发的价格调节范围设置最小值
      max: 0.2,  // 根据你算法下发的价格调节范围设置最大值
      calculable: true,
      inRange: {
        color: ['#00fa9a', '#f4e925', '#ff4500'] // 绿(降价放电) -> 黄 -> 红(涨价抑制)
      },
      textStyle: { color: '#ccc' },
      bottom: '10%',
      left: '3%'
    },
    // 3. 配置真实的地理坐标系底图外观
    geo: {
      map: 'shenzhen',
      roam: true, // 开启鼠标缩放和平移拖拽
      zoom: 1.1,
      label: { emphasis: { show: false } },
      itemStyle: {
        normal: {
          areaColor: '#0a1a2a', // 地图板块底色
          borderColor: '#00eaff', // 科技蓝边框
          borderWidth: 1
        },
        emphasis: {
          areaColor: '#1a2e40' // 鼠标悬浮时的板块颜色
        }
      }
    },
    series: [
      {
        name: 'V2G 调控节点',
        type: 'effectScatter', // 涟漪特效散点
        coordinateSystem: 'geo', // 绑定到前面的 geo 坐标系
        symbolSize: 8,
        rippleEffect: { brushType: 'stroke', scale: 3 },
        data: []
      }
    ]
  };

  chartInstance.setOption(option);
  window.addEventListener('resize', () => chartInstance.resize());
});

// 4. 监听云端下发的数据并渲染真实节点
watch(() => systemState.stations, (newStations) => {
  if (chartInstance && newStations && newStations.length > 0) {
    // 解构 Proxy，防止报错
    const rawStations = [...newStations];
    const realNodes = [];

    rawStations.forEach((val, idx) => {
      // 兼容数组格式的坐标映射
      // 假设 node_coordinates.json 的格式是: { "0": [114.05, 22.54], "1": [...] }
      const coord = geoCoordMap[String(idx)] || geoCoordMap[idx];

      if (coord && coord.length === 2) {
        realNodes.push({
          name: String(idx),
          value: [coord[0], coord[1], val] // [经度, 纬度, 算法下发的调价系数]
        });
      }
    });

    // 动态更新节点数据
    chartInstance.setOption({
      series: [{ data: realNodes }]
    });
  }
}, { deep: true, immediate: true });
</script>

<style scoped>
.component-wrapper { display: flex; flex-direction: column; height: 100%; width: 100%; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.panel-title { margin: 0; font-size: 1.1rem; font-weight: 600; color: #00eaff; }
.echarts-container { flex: 1; min-height: 400px; }
</style>