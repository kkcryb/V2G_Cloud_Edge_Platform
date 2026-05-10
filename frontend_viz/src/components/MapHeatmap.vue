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

// 🚨 【重要】你需要在这里引入深圳市的 GeoJSON 文件
// import shenzhenGeoJson from '../assets/shenzhen.json';
// 🚨 【重要】你需要在这里引入 275 个节点的经纬度映射 (ID -> [经度, 纬度])
// import geoCoordMap from '../assets/node_coordinates.json';

const chartRef = ref(null);
let chartInstance = null;

// Mock 坐标系，防止无数据时报错 (你需要用真实的替换这段)
const mockGeoCoordMap = {};
for(let i=0; i<275; i++) {
  mockGeoCoordMap[i] = [113.8 + Math.random()*0.5, 22.5 + Math.random()*0.3];
}

onMounted(() => {
  chartInstance = echarts.init(chartRef.value);

  // 注册地图 (假设你有了 shenzhenGeoJson)
  // echarts.registerMap('shenzhen', shenzhenGeoJson);

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: function (params) {
        return `节点 ID: ${params.data.name}<br/>调价系数: ${params.data.value[2]}`;
      }
    },
    visualMap: {
      type: 'continuous',
      min: -1,
      max: 1, // 根据你的 r_opt 弹性范围调整
      calculable: true,
      inRange: { color: ['#00fa9a', '#1e90ff', '#ff4500'] }, // 绿->蓝->红
      text: ['高压区 (提价)', '低压区 (降价)'],
      textStyle: { color: '#00eaff' },
      bottom: 20,
      left: 20
    },
    geo: {
      map: 'shenzhen', // 如果没有 GeoJSON，可以暂时去掉 geo 配置，改用 grid 散点
      roam: true,
      itemStyle: {
        areaColor: '#0a1a3a', // 科技蓝底图
        borderColor: '#00eaff',
        borderWidth: 1
      },
      emphasis: { itemStyle: { areaColor: '#1e90ff' } }
    },
    series: [
      {
        name: 'V2G Nodes',
        type: 'effectScatter', // 涟漪特效散点
        coordinateSystem: 'geo',
        symbolSize: 8,
        rippleEffect: {
          brushType: 'stroke',
          scale: 3
        },
        data: []
      }
    ]
  };

  // 如果暂时没有 GeoJSON，降级为普通笛卡尔坐标系的散点图查看效果
  if (!echarts.getMap('shenzhen')) {
    option.geo = undefined;
    option.xAxis = { show: false, scale: true };
    option.yAxis = { show: false, scale: true };
    option.series[0].coordinateSystem = 'cartesian2d';
  }

  chartInstance.setOption(option);
  window.addEventListener('resize', () => chartInstance.resize());
});

watch(() => systemState.stations, (newStations) => {
  if (chartInstance && newStations && newStations.length > 0) {
    const realNodes = newStations.map((item, idx) => {
      const val = typeof item === 'object' ? item.value : item;
      const coord = mockGeoCoordMap[idx]; // 替换为真实的 geoCoordMap
      return {
        name: String(idx),
        value: [coord[0], coord[1], val] // [经度, 纬度, 调价系数]
      };
    });

    chartInstance.setOption({
      series: [{ data: realNodes }]
    });
  }
}, { deep: true });
</script>

<style scoped>
.component-wrapper { height: 100%; display: flex; flex-direction: column; }
.panel-header { position: absolute; top: 20px; left: 20px; z-index: 5; }
.panel-title { color: #00eaff; font-size: 1.2rem; font-weight: 600; text-shadow: 0 0 10px rgba(0, 234, 255, 0.5); }
.echarts-container { flex: 1; width: 100%; height: 100%; }
</style>