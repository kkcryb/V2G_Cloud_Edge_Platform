import numpy as np
import pandas as pd
import warnings
import torch
import torch.nn as nn
import torch.optim as optim
from scipy.optimize import minimize
import time
import json
import uuid
import requests
from datetime import datetime
import paho.mqtt.client as mqtt
from apscheduler.schedulers.blocking import BlockingScheduler
from shared_lib.config import config

warnings.filterwarnings('ignore')

# ==========================================
# 🎯 全局参数配置区
# ==========================================
SEED = 50
N_AREAS = 275
ELASTICITY_RANGE = (-0.7, 1.1)
GRID_PRICE = 0.7

ADMM_MAX_ITER = 30
VAE_EPOCHS = 5
Y_MAX_RATIO = 0.15
BAYESIAN_TRIALS = 15


# ==========================================
# 🧬 【核心网络】条件变分自编码器 (CVAE) (保持原样)
# ==========================================
class V2G_CVAE(nn.Module):
    def __init__(self, input_dim=5, latent_dim=8):
        super(V2G_CVAE, self).__init__()
        self.enc = nn.Sequential(nn.Linear(input_dim, 32), nn.ReLU(), nn.Linear(32, 16), nn.ReLU())
        self.fc_mu = nn.Linear(16, latent_dim)
        self.fc_logvar = nn.Linear(16, latent_dim)
        self.dec = nn.Sequential(nn.Linear(latent_dim, 16), nn.ReLU(), nn.Linear(16, 32), nn.ReLU())
        self.out_r = nn.Linear(32, 1)
        self.out_y = nn.Linear(32, 1)

    def encode(self, x):
        h = self.enc(x)
        return self.fc_mu(h), self.fc_logvar(h)

    def decode(self, z):
        h = self.dec(z)
        r_pred = torch.tanh(self.out_r(h)) * 1.0 + 0.2
        y_pred = torch.sigmoid(self.out_y(h))
        return r_pred, y_pred

    def forward(self, x):
        mu, logvar = self.encode(x)
        std = torch.exp(0.5 * logvar)
        z = mu + torch.randn_like(std) * std
        r_pred, y_pred = self.decode(z)
        return r_pred, y_pred, mu, logvar


# ==========================================
# 🔥 【深度融合内核】VAE 热启动 + 数学精确求解 (保持原样)
# ==========================================
class V2GEnvironment:
    def __init__(self, L_base, elasticity, C_price, C_grid):
        self.L_base = L_base
        self.elasticity = elasticity
        self.C_price = C_price
        self.C_grid = C_grid
        self.n_areas = len(L_base)
        self.r_limit = [-0.8, 1.2]
        self.y_limit = [0, np.max(L_base) * Y_MAX_RATIO]
        self.y_max_arr = np.full(self.n_areas, self.y_limit[1])

    def evaluate(self, r, y):
        r = np.clip(r, self.r_limit[0], self.r_limit[1])
        y = np.clip(y, self.y_limit[0], self.y_limit[1])
        L_opt = self.L_base * (1 + self.elasticity * r) - y
        f1_std = np.std(L_opt)
        f2_rev = np.sum(self.C_price * (1 + r) * (self.L_base * (1 + self.elasticity * r)) + self.C_grid * y)
        return f1_std, f2_rev, L_opt


def run_vae_ws_admm(env, w1, w2, rho_init, max_iter=30):
    # (算法实现保持不变，此处简写以突出系统架构...)
    # 实际使用中请保持你原本长达百行的 ADMM 求解逻辑
    rho, rho_min, rho_max = rho_init, 0.1, 100.0
    mu_res, tau_incr, tau_decr = 10.0, 2.0, 2.0
    z, z_prev, l_val, lam = env.L_base.copy(), env.L_base.copy(), env.L_base.copy(), np.zeros(env.n_areas)
    alpha, z_hat = 1.0, env.L_base.copy()
    r_opt_exact, y_opt_exact = np.zeros(env.n_areas), np.zeros(env.n_areas)

    vae_agent = V2G_CVAE()
    optimizer = optim.Adam(vae_agent.parameters(), lr=0.01)

    T_L = torch.FloatTensor(env.L_base).unsqueeze(1)
    T_E = torch.FloatTensor(env.elasticity).unsqueeze(1)
    T_C = torch.FloatTensor(env.C_price).unsqueeze(1)
    T_YMAX = torch.FloatTensor(env.y_max_arr).unsqueeze(1)

    for step in range(max_iter):
        T_lam = torch.FloatTensor(lam).unsqueeze(1)
        T_zhat = torch.FloatTensor(z_hat).unsqueeze(1)
        features = torch.cat([T_L, T_E, T_C, T_lam, T_zhat], dim=1)

        vae_agent.eval()
        with torch.no_grad():
            r_pred_t, y_ratio_t, _, _ = vae_agent(features)
            r_pred = r_pred_t.squeeze().numpy()
            y_pred = (y_ratio_t * T_YMAX).squeeze().numpy()

        for i in range(env.n_areas):
            def local_obj(vars):
                r, y = vars
                l_i = env.L_base[i] * (1 + env.elasticity[i] * r) - y
                rev_i = env.C_price[i] * (1 + r) * env.L_base[i] * (1 + env.elasticity[i] * r) + env.C_grid * y
                return -w2 * rev_i + lam[i] * l_i + (rho / 2.0) * (l_i - z_hat[i]) ** 2

            bounds = [(env.r_limit[0], env.r_limit[1]), (env.y_limit[0], env.y_limit[1])]
            x0 = [np.clip(r_pred[i], env.r_limit[0], env.r_limit[1]),
                  np.clip(y_pred[i], env.y_limit[0], env.y_limit[1])]
            res = minimize(local_obj, x0, bounds=bounds, method='L-BFGS-B', options={'maxiter': 10})
            r_opt_exact[i], y_opt_exact[i] = res.x
            l_val[i] = env.L_base[i] * (1 + env.elasticity[i] * r_opt_exact[i]) - y_opt_exact[i]

        v = l_val + lam / rho
        v_mean = np.mean(v)
        z_new = (rho * v + 2 * w1 / env.n_areas * v_mean) / (rho + 2 * w1 / env.n_areas)
        alpha_new = (1 + np.sqrt(1 + 4 * alpha ** 2)) / 2.0
        z_hat = z_new + ((alpha - 1) / alpha_new) * (z_new - z)
        alpha, z = alpha_new, z_new
        lam = lam + rho * (l_val - z_hat)

    return r_opt_exact, y_opt_exact


def bayesian_tune_vae_admm(env, trials=5):  # 为演示加快速度，设为5
    import optuna
    def objective(trial):
        w1 = trial.suggest_float('w1', 10, 5000, log=True)
        w2 = trial.suggest_float('w2', 0.1, 20)
        rho = trial.suggest_float('rho_init', 0.5, 10)
        r, y = run_vae_ws_admm(env, w1, w2, rho, max_iter=5)
        f1, f2, _ = env.evaluate(r, y)
        norm_f1 = f1 / np.std(env.L_base)
        norm_f2 = 1 - (f2 / 10000)
        return np.sqrt(norm_f1 ** 2 + norm_f2 ** 2)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    best_param = study.best_params
    r, y = run_vae_ws_admm(env, **best_param, max_iter=ADMM_MAX_ITER)
    return r, y


# ==========================================
# 🔌 真实系统对接层
# ==========================================

class RealAIModelClient:
    """对接真实的 FastAPI AI 微服务"""

    @staticmethod
    def get_predictions(current_hour):
        print(f"[AI 大脑] 正在请求 {current_hour}:00 的基准负荷与弹性系数...")
        # 方案A: 如果 AI 是独立微服务，发起真实 HTTP 请求
        # response = requests.get(f"http://ai-service:8000/api/predict?hour={current_hour}")
        # data = response.json()
        # return np.array(data['predicted_load']), np.array(data['elasticity_coefficient']), np.array(data['base_price'])

        # 方案B: 本地单机闭环仿真模式 (单体调用)
        from ai_prediction.services.inference_service import inference_service
        # 这里需要传入历史特征和邻接矩阵，具体视你的特征获取逻辑而定
        # result = inference_service.predict_and_evaluate_elasticity(historical_features, adj_matrix)
        # return np.array(result['predicted_load']), np.array(result['elasticity_coefficient']), np.array(result['base_price'])

        # 为了演示代码可直接运行，暂时保留随机生成，但接入了 config
        import numpy as np
        np.random.seed(current_hour)
        predicted_load = np.random.normal(110, 8, config.N_AREAS)
        predicted_elasticity = np.random.uniform(config.ELASTICITY_RANGE[0], config.ELASTICITY_RANGE[1], config.N_AREAS)
        base_price = np.random.uniform(0.6, 0.8, config.N_AREAS)
        return predicted_load, predicted_elasticity, base_price


class RealMQTTEdgeClient:
    """真实的 MQTT 下发模块，直连 EMQX"""

    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        try:
            self.client.connect(config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE)
            self.client.loop_start()
            print("✅ [运筹层 MQTT] 已成功连接到消息总线")
        except Exception as e:
            print(f"❌ [运筹层 MQTT] 连接失败: {e}")

    def dispatch_commands(self, current_hour, r_opt, y_opt):
        schedule_id = f"SCH_{datetime.now().strftime('%Y%m%d%H')}"
        print(f"[阶段一指令下发] 正在向 {config.N_AREAS} 个边缘节点下发1小时级调度目标...")

        for area_id in range(config.N_AREAS):
            # 组装符合 data_hub/main.py 预期的数据格式
            payload = {
                "schedule_id": schedule_id,
                "node_id": area_id,
                "price_adj_rate": round(r_opt[area_id], 4),  # 指令A: 调价率
                "power_set": round(y_opt[area_id], 2),  # 指令B: 目标放电量(kW或kWh)
                "duration": config.MACRO_INTERVAL,  # 持续时间: 3600秒 (1小时)
                "timestamp": datetime.now().isoformat()
            }

            # 发布调度指令到主题 v2g/cloud/schedule
            self.client.publish(config.TOPIC_CLOUD_SCHEDULE, json.dumps(payload))

            # 仅打印前3个作为日志
            if area_id < 3:
                print(
                    f"   => [节点 {area_id:03d}] 调价: {payload['price_adj_rate'] * 100:+.1f}% | 目标放电: {payload['power_set']} kW")


# ==========================================
# ⚙️ 阶段一：云端宏观规划引擎 (真实业务流)
# ==========================================

class CloudDecisionEngine:
    def __init__(self):
        self.ai_client = RealAIModelClient()
        self.mqtt_client = RealMQTTEdgeClient()

    def run_stage_one_dispatch(self):
        """执行流程图中的：阶段一：云端宏观规划（1小时级调度）"""
        current_hour = datetime.now().hour
        print("\n" + "=" * 60)
        print(f"🕒 触发系统时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 开始阶段一宏观规划")
        print("=" * 60)

        # 1. & 2. 获取数据与 AI 预测
        pred_L, pred_E, pred_C = self.ai_client.get_predictions(current_hour)

        # 3. 构建运筹调度环境并寻优 (调用原本的 VAE-WS-ADMM)
        print(f"[运筹引擎] 启动多目标优化 (基于 VAE 热启动与 ADMM)...")
        start_time = time.time()
        # 注意这里传入 config.GRID_PRICE
        env = V2GEnvironment(pred_L, pred_E, pred_C, config.GRID_PRICE)
        r_opt, y_opt = bayesian_tune_vae_admm(env, trials=config.BAYESIAN_TRIALS)
        print(f"[运筹引擎] 优化计算完成，耗时: {time.time() - start_time:.2f} 秒")

        # 4. 指令解析与真实 MQTT 下发
        self.mqtt_client.dispatch_commands(current_hour, r_opt, y_opt)

        print("-" * 60)
        print(f"✅ {current_hour}:00 宏观调度指令下发完毕。等待边缘端进行 5 分钟级滚动追踪...")


# ==========================================
# 🚀 平台启动入口 (真实时间调度)
# ==========================================
if __name__ == '__main__':
    engine = CloudDecisionEngine()

    if config.SIMULATION_MODE:
        # 如果是单机快速仿真模式，直接跑几个小时测试
        for hour in [8, 9, 10]:
            engine.run_stage_one_dispatch()
            time.sleep(2)
    else:
        # 生产环境模式：启动 APScheduler，每个小时的第 00 分 00 秒触发一次
        scheduler = BlockingScheduler(timezone="Asia/Shanghai")
        # 设定在每小时的 0 分钟执行
        scheduler.add_job(engine.run_stage_one_dispatch, 'cron', minute=0)

        print("⏱️ 云端决策引擎已启动，等待整点触发...")
        # 启动时可以先强制执行一次以初始化状态
        engine.run_stage_one_dispatch()
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass