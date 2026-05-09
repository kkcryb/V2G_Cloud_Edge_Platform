import { reactive } from 'vue';

// 全局响应式状态，组件直接绑定这些数据
export const systemState = reactive({
  isConnected: false,
  // 阶段一：1小时级云端调度数据
  stations: [],           // 拓扑节点 (adj.csv / distance.csv 映射)
  cloudTargetCurve: [],   // VAE-WS-ADMM 优化的目标轨迹 (1小时)
  baselineCurve: [],      // AI大脑预测的初始基线

  // 阶段二：5分钟级边缘微观控制数据
  actualLoadCurve: [],    // 边缘端实时回传的实际负荷
  currentStep: 0,         // 当前5分钟所在的步数 (0-11)

  // 阶段三与KPI评估
  v2gProgress: 0,         // V2G 100kWh 放电任务进度
  greenEnergyRate: 0,     // 绿电消纳率
  totalCost: 0            // 运行成本
});

export function initWebSocket(wsUrl = 'ws://127.0.0.1:8000/ws/dashboard') {
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => { systemState.isConnected = true; };
  ws.onclose = () => { systemState.isConnected = false; };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    // 核心事件路由机制
    switch (data.event_type) {
      case 'INIT_TOPOLOGY':
        systemState.stations = data.payload.stations;
        break;

      case 'CLOUD_DISPATCH_1H':
        // 8:00 云端下发宏观指令，重置或更新曲线
        systemState.baselineCurve = data.payload.baseline;
        systemState.cloudTargetCurve = data.payload.target;
        // 清空上一小时的实际追踪数据，准备接受新的5分钟数据
        systemState.actualLoadCurve = [];
        break;

      case 'EDGE_MICRO_UPDATE_5MIN':
        // 8:05, 8:10... 边缘端滚动控制回调
        systemState.actualLoadCurve.push([
          data.payload.timestamp,
          data.payload.actual_load
        ]);
        systemState.currentStep = data.payload.step;
        systemState.v2gProgress = data.payload.v2g_progress;
        systemState.nodeDetails = data.payload.node_details;
        break;

      case 'PHASE_END_WRITEBACK':
        // 9:00 阶段三数据回写完毕，更新综合KPI
        systemState.greenEnergyRate = data.payload.green_rate;
        systemState.totalCost = data.payload.cost;
        break;
    }
  };

  return ws;
}