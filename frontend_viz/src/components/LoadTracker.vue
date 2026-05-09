<template>
  <div class="component-wrapper">
    <!-- 顶部标题 -->
    <div class="panel-header">
      <div>
        <h3 class="panel-title">
          📉 5分钟级滚动追踪
          <span class="sub-title">
            （云端宏观规划 vs 边端微观执行）
          </span>
        </h3>

        <div class="term-explanations">
          <span title="GCN-LSTM预测得到的无控制自然负荷">
            ❓ AI预测基线
          </span>

          |

          <span title="云端VAE-WS-ADMM计算的未来1小时优化目标">
            ❓ 运筹规划目标
          </span>

          |

          <span title="边缘节点每5分钟执行MQTT控制后的真实负荷">
            ❓ 实际执行轨迹
          </span>

          |

          <span title="实际执行与目标轨迹之间的误差">
            ❓ Tracking Error
          </span>
        </div>
      </div>

      <!-- 状态角标 -->
      <div class="status-box">
        <div class="status-item">
          <span class="dot online"></span>
          边端在线
        </div>

        <div class="status-item">
          当前步长：
          <strong>{{ currentStep }}</strong>
        </div>
      </div>
    </div>

    <!-- 图表 -->
    <div ref="chartRef" class="echarts-container"></div>
  </div>
</template>

<script setup>
import {
  ref,
  onMounted,
  onUnmounted,
  watch
} from 'vue';

import * as echarts from 'echarts';
import { systemState } from '../store/wsStore';

const chartRef = ref(null);

let chartInstance = null;

/**
 * 当前滚动步长
 */
const currentStep = ref(0);

/**
 * 安全数据格式化
 * 统一转为 [[x,y], ...]
 */
const formatToCoordinates = (arr = []) => {
  if (!Array.isArray(arr)) return [];

  // 已经是二维坐标
  if (Array.isArray(arr[0])) {
    return arr.filter(
      item =>
        Array.isArray(item) &&
        item.length >= 2 &&
        Number.isFinite(item[0]) &&
        Number.isFinite(item[1])
    );
  }

  // 一维数组转二维
  return arr
    .filter(v => Number.isFinite(v))
    .map((val, idx) => [idx, val]);
};

/**
 * Tracking Error
 * actual - target
 */
const computeErrorArea = (actual, target) => {
  const result = [];

  const len = Math.min(actual.length, target.length);

  for (let i = 0; i < len; i++) {
    const actualY = actual[i][1];
    const targetY = target[i][1];

    if (
      Number.isFinite(actualY) &&
      Number.isFinite(targetY)
    ) {
      result.push([
        actual[i][0],
        actualY - targetY
      ]);
    }
  }

  return result;
};

/**
 * 初始化图表
 */
const initChart = () => {
  if (!chartRef.value) return;

  chartInstance = echarts.init(chartRef.value);

  const option = {
    backgroundColor: 'transparent',

    animation: true,

    tooltip: {
      trigger: 'axis',

      axisPointer: {
        type: 'cross'
      },

      backgroundColor: 'rgba(20,20,20,0.92)',

      borderColor: '#444',

      textStyle: {
        color: '#eee'
      },

      formatter: params => {
        if (!params?.length) return '';

        const step = params[0].axisValue;

        let html = `
          <div style="margin-bottom:6px;">
            <strong>滚动步长：${step}</strong>
          </div>
        `;

        let actual = null;
        let target = null;

        params.forEach(item => {
          const value = item.data?.[1];

          html += `
            <div style="margin:3px 0;">
              <span style="
                display:inline-block;
                width:10px;
                height:10px;
                border-radius:50%;
                background:${item.color};
                margin-right:6px;
              "></span>

              ${item.seriesName}：
              <strong>${Number(value).toFixed(2)} kW</strong>
            </div>
          `;

          if (item.seriesId === 'actual') {
            actual = value;
          }

          if (item.seriesId === 'target') {
            target = value;
          }
        });

        if (
          Number.isFinite(actual) &&
          Number.isFinite(target)
        ) {
          const error = actual - target;

          html += `
            <hr style="border-color:#333;" />

            <div>
              Tracking Error：
              <strong style="
                color:${Math.abs(error) > 5 ? '#ff4500' : '#00fa9a'}
              ">
                ${error.toFixed(2)} kW
              </strong>
            </div>
          `;
        }

        return html;
      }
    },

    legend: {
      top: 0,

      textStyle: {
        color: '#ccc'
      },

      data: [
        'AI预测基线',
        '运筹规划目标',
        '实际执行轨迹',
        'Tracking Error'
      ]
    },

    grid: {
      left: '4%',
      right: '4%',
      bottom: '8%',
      top: '16%',
      containLabel: true
    },

    xAxis: {
      type: 'value',

      name: '5分钟步长',

      min: 0,

      max: value => {
        return Math.max(11, value.max);
      },

      axisLine: {
        lineStyle: {
          color: '#666'
        }
      },

      axisLabel: {
        color: '#aaa',
        formatter: val => `T${val}`
      },

      splitLine: {
        lineStyle: {
          color: '#222'
        }
      }
    },

    yAxis: {
      type: 'value',

      name: '总负荷 (kW)',

      nameTextStyle: {
        color: '#aaa'
      },

      axisLine: {
        lineStyle: {
          color: '#666'
        }
      },

      axisLabel: {
        color: '#aaa'
      },

      splitLine: {
        lineStyle: {
          color: '#333',
          type: 'dashed'
        }
      }
    },

    series: [
      /**
       * AI预测基线
       */
      {
        id: 'baseline',

        name: 'AI预测基线',

        type: 'line',

        smooth: true,

        showSymbol: false,

        z: 1,

        lineStyle: {
          color: '#777',
          width: 2,
          type: 'dashed'
        },

        areaStyle: {
          color: 'rgba(120,120,120,0.06)'
        },

        data: []
      },

      /**
       * 运筹规划目标
       */
      {
        id: 'target',

        name: '运筹规划目标',

        type: 'line',

        smooth: true,

        showSymbol: false,

        z: 3,

        lineStyle: {
          color: '#00fa9a',
          width: 4
        },

        emphasis: {
          focus: 'series'
        },

        data: []
      },

      /**
       * 实际执行轨迹
       */
      {
        id: 'actual',

        name: '实际执行轨迹',

        type: 'line',

        smooth: true,

        z: 5,

        showSymbol: true,

        symbol: 'circle',

        symbolSize: val => {
          return val[0] === currentStep.value
            ? 10
            : 5;
        },

        lineStyle: {
          color: '#ff4500',
          width: 3
        },

        itemStyle: {
          color: '#ff4500'
        },

        areaStyle: {
          color: new echarts.graphic.LinearGradient(
            0,
            0,
            0,
            1,
            [
              {
                offset: 0,
                color: 'rgba(255,69,0,0.28)'
              },
              {
                offset: 1,
                color: 'rgba(255,69,0,0)'
              }
            ]
          )
        },

        data: []
      },

      /**
       * Tracking Error
       */
      {
        id: 'error',

        name: 'Tracking Error',

        type: 'bar',

        z: 0,

        barWidth: 10,

        itemStyle: {
          color: params => {
            return Math.abs(params.value[1]) > 5
              ? '#ff4500'
              : '#00bfff';
          },

          opacity: 0.35
        },

        data: []
      }
    ]
  };

  chartInstance.setOption(option);
};

/**
 * 更新图表
 */
const updateChart = () => {
  if (!chartInstance) return;

  const baseline = formatToCoordinates(
    systemState.baselineCurve
  );

  const target = formatToCoordinates(
    systemState.cloudTargetCurve
  );

  const actual = formatToCoordinates(
    systemState.actualLoadCurve
  );

  const errorData = computeErrorArea(
    actual,
    target
  );

  // 当前步长
  if (actual.length > 0) {
    currentStep.value =
      actual[actual.length - 1][0];
  }

  chartInstance.setOption({
    series: [
      {
        id: 'baseline',
        data: baseline
      },

      {
        id: 'target',
        data: target
      },

      {
        id: 'actual',
        data: actual,

        // 大数据量关闭symbol
        showSymbol: actual.length <= 30
      },

      {
        id: 'error',
        data: errorData
      }
    ]
  });
};

/**
 * resize
 */
const handleResize = () => {
  chartInstance?.resize();
};

onMounted(() => {
  initChart();

  updateChart();

  window.addEventListener(
    'resize',
    handleResize
  );
});

/**
 * 销毁
 */
onUnmounted(() => {
  window.removeEventListener(
    'resize',
    handleResize
  );

  chartInstance?.dispose();

  chartInstance = null;
});

/**
 * 同时监听三条曲线
 */
watch(
  () => [
    systemState.baselineCurve,
    systemState.cloudTargetCurve,
    systemState.actualLoadCurve
  ],
  () => {
    updateChart();
  },
  {
    deep: false
  }
);
</script>

<style scoped>
.component-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

/* =========================
   Header
========================= */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;

  margin-bottom: 8px;
}

.panel-title {
  margin: 0;

  font-size: 1rem;
  font-weight: 600;

  color: #00bfff;
}

.sub-title {
  font-size: 0.82rem;
  color: #888;
  font-weight: 400;
}

.term-explanations {
  margin-top: 4px;

  font-size: 0.74rem;
  color: #888;
}

.term-explanations span {
  cursor: help;

  border-bottom: 1px dotted #555;

  transition: 0.2s;
}

.term-explanations span:hover {
  color: #ddd;
}

/* =========================
   Status
========================= */
.status-box {
  display: flex;
  flex-direction: column;
  align-items: flex-end;

  gap: 4px;

  font-size: 0.75rem;
  color: #aaa;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.online {
  background: #00fa9a;

  box-shadow: 0 0 8px #00fa9a;
}

/* =========================
   Chart
========================= */
.echarts-container {
  flex: 1;
  min-height: 300px;
}

/* =========================
   Responsive
========================= */
@media (max-width: 900px) {
  .panel-header {
    flex-direction: column;
    gap: 10px;
  }

  .status-box {
    align-items: flex-start;
  }
}
</style>