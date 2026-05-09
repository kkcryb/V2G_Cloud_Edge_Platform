# system_runner.py (放于项目根目录)
import time
import requests
import numpy as np
import torch
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from shared_lib.config import config
from optimization.main import V2GEnvironment, bayesian_tune_vae_admm, RealMQTTEdgeClient
from ai_prediction.services.inference_service import inference_service


class GlobalOrchestrator:
    def __init__(self):
        self.mqtt_client = RealMQTTEdgeClient()
        self.ai_service = inference_service
        # 加载 AI 模型所需的空间图邻接矩阵 (提前加载好)
        self.adj_matrix = np.loadtxt("ai_prediction/training/data/adj.csv", delimiter=",")

    def fetch_historical_data_from_hub(self):
        """1. 从数据中台拉取过去24小时的真实边缘执行数据"""
        print("[调度器] 正在从 Data Hub 提取过去 24 小时真实仿真负荷...")
        try:
            # 假设你的 Data Hub 运行在本地 8081 端口
            # 真实开发中，这里你需要从 API 拼装出 (275, 24) 的负荷矩阵
            # 为了防止 HTTP 请求失败导致系统崩溃，建议提供一个 Fallback 机制

            # TODO: 使用 requests.get(f"http://127.0.0.1:{config.WS_PORT}/api/v1/history/power?...")
            # 提取全网 N_AREAS 的过去 24 个小时点位

            # 占位：模拟成功从 InfluxDB 提取并聚合成 (N_AREAS, 24) 的矩阵
            historical_load = np.random.normal(50, 10, (config.N_AREAS, config.SEQ_LEN))
            return historical_load
        except Exception as e:
            print(f"❌ [调度器] 数据拉取失败，使用容灾默认值: {e}")
            return np.ones((config.N_AREAS, config.SEQ_LEN)) * 50

    def prepare_ai_tensors(self, historical_load):
        """2. 对齐 AI 模型的输入维度特征 (极其关键)"""
        # AI 模型输入维度是 [batch, seq_len=24, num_nodes=275, input_dim=5]
        # input_dim=5 分别可能是: [power_kw, e_price, occupancy, temperature, wind]
        # 由于仿真器只回写了 power_kw，我们需要把其他的环境特征用静态数据补齐

        batch_size = 1
        tensor_data = np.zeros((batch_size, config.SEQ_LEN, config.NUM_NODES, 2))

        for seq_idx in range(config.SEQ_LEN):
            for node_idx in range(config.NUM_NODES):
                tensor_data[0, seq_idx, node_idx, 0] = historical_load[node_idx, seq_idx]  # 真实的负荷特征
                tensor_data[0, seq_idx, node_idx, 1] = 0.6  # 默认电价补齐
                #tensor_data[0, seq_idx, node_idx, 2] = 0.5  # 默认占有率补齐
                #tensor_data[0, seq_idx, node_idx, 3] = 25.0  # 默认温度补齐
                #tensor_data[0, seq_idx, node_idx, 4] = 2.0  # 默认风速补齐

        return tensor_data

    def run_hourly_dispatch(self):
        """【核心闭环】一小时级宏观规划全流程"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print("\n" + "🚀" * 30)
        print(f"🕒 触发系统全局调度时间: {current_time} | 开始云端宏观规划")
        print("🚀" * 30)

        # ==========================================
        # Step 1: 感知 (读取 Data Hub 数据)
        # ==========================================
        hist_load_2d = self.fetch_historical_data_from_hub()
        hist_features_4d = self.prepare_ai_tensors(hist_load_2d)

        # ==========================================
        # Step 2: 预测 (调用 GCN-LSTM 与 弹性推演)
        # ==========================================
        print("[AI 预测脑] 正在执行时空图模型推理与微观经济扰动计算...")
        ai_result = self.ai_service.predict_and_evaluate_elasticity(hist_features_4d, self.adj_matrix)

        # 提取下一小时的预测数据 (提取 seq_len 的第一个时间步 T+1)
        pred_L = np.array(ai_result["predicted_load"])[:, 0]  # 未来1小时负荷
        pred_E = np.array(ai_result["elasticity_coefficient"])[:, 0]  # 未来1小时弹性
        pred_C = np.ones(config.N_AREAS) * 0.7  # 基础电价

        # ==========================================
        # Step 3: 决策 (运筹引擎寻优)
        # ==========================================
        print(f"[运筹决策核心] 启动多目标 VAE-WS-ADMM 联合优化...")
        start_time = time.time()
        env = V2GEnvironment(pred_L, pred_E, pred_C, config.GRID_PRICE)
        r_opt, y_opt = bayesian_tune_vae_admm(env, trials=config.BAYESIAN_TRIALS)
        print(f"[运筹决策核心] 优化帕累托前沿寻找完毕，耗时: {time.time() - start_time:.2f} 秒")

        # ==========================================
        # Step 4: 执行 (MQTT 指令下发给边缘集群)
        # ==========================================
        self.mqtt_client.dispatch_commands(datetime.now().hour, r_opt, y_opt)

        print("✅ 本轮云端调度闭环执行完毕！边缘集群已接管微观控制。")


if __name__ == '__main__':
    orchestrator = GlobalOrchestrator()

    if config.SIMULATION_MODE:
        # 单机仿真加速：不用等真的一个小时，直接连续跑3个调度周期
        for i in range(24):
            orchestrator.run_hourly_dispatch()
            # 留出10秒时间给 EdgeSimulator 疯狂执行微观5分钟步长并回写数据库
            print("⏳ 等待边缘集群进行微观响应回写...")
            time.sleep(10)
    else:
        # 生产环境：真正按照时钟，每小时0分0秒触发一次
        scheduler = BlockingScheduler(timezone="Asia/Shanghai")
        scheduler.add_job(orchestrator.run_hourly_dispatch, 'cron', minute=0)
        print("⏱️ 云边协同系统心脏已启动，等待整点心跳触发...")
        orchestrator.run_hourly_dispatch()  # 启动先跑一次
        scheduler.start()