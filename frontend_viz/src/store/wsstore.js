import { reactive } from 'vue';

// 全局响应式状态
export const systemState = reactive({
  isConnected: false,
  stations: [],
  cloudTargetCurve: [],   // 运筹优化的目标轨迹
  baselineCurve: [],      // AI预测的初始基线
  actualLoadCurve: [],    // 边缘端实时轨迹
  currentStep: 0,
  nodeDetails: {},        // 预定义节点明细字典
  v2gProgress: 0,
  greenEnergyRate: 0,
  totalCost: 0
});

export function initWebSocket(wsUrl = 'ws://127.0.0.1:8000/ws/dashboard') {
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => { systemState.isConnected = true; };
  ws.onclose = () => { systemState.isConnected = false; };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.event_type) {
      case 'INIT_TOPOLOGY':
        systemState.stations = data.payload.stations;
        break;

      case 'CLOUD_DISPATCH_1H':
        // 进入新的一小时调度
        systemState.baselineCurve = data.payload.baseline;
        systemState.cloudTargetCurve = data.payload.target;
        if (data.payload.price_adjustments) {
            systemState.stations = data.payload.price_adjustments;
        }
        // 清空轨迹
        systemState.actualLoadCurve = [];
        systemState.currentStep = 0;
        break;

      case 'EDGE_MICRO_UPDATE_5MIN':
        // 🚨 核心修复：直接覆盖为后端传来的完整 actual_curve
        // 这样可以确保 X 轴是 [0, 1, 2...] 的数字步长，与图表坐标系完美匹配
        systemState.actualLoadCurve = data.payload.actual_curve;

        systemState.currentStep = data.payload.step;
        systemState.nodeDetails = data.payload.node_details;

        // 如果后端传了进度则更新
        if (data.payload.v2g_progress !== undefined) {
          systemState.v2gProgress = data.payload.v2g_progress;
        }
        break;

      case 'PHASE_END_WRITEBACK':
        systemState.greenEnergyRate = data.payload.green_rate;
        systemState.totalCost = data.payload.cost;
        break;
    }
  };

  return ws;
}
