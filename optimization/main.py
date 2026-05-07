import numpy as np
import pandas as pd
import warnings
import torch
import torch.nn as nn
import torch.optim as optim
from scipy.optimize import minimize
import time

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
# 🔌 云边架构系统对接插槽 (System Interface Mocks)
# ==========================================

class Layer1_DatabaseMock:
    """Mock InfluxDB：读取历史 24 小时数据"""

    @staticmethod
    def get_historical_data(current_hour):
        print(f"[层1 - 数据库] 从 InfluxDB 拉取 {current_hour}:00 之前的 24 小时边缘端仿真回写数据...")
        # 实际开发中这里是 InfluxDB Client 查询代码
        return {"status": "ok", "data_len": 24}


class Layer2_AIModelMock:
    """Mock FastAPI AI微服务：预测下一小时负载与价格弹性"""

    @staticmethod
    def predict_next_hour(history_data, current_hour):
        print(
            f"[层2 - AI大脑] 调用 Docker 容器化的时空图 AI 微服务，生成 {current_hour}:00 - {current_hour + 1}:00 的预测...")
        # 实际开发中： response = requests.post("http://ai-service:8000/predict", json=history_data)
        np.random.seed(current_hour)
        predicted_load = np.random.normal(110, 8, N_AREAS)
        predicted_elasticity = np.random.uniform(ELASTICITY_RANGE[0], ELASTICITY_RANGE[1], N_AREAS)
        base_price = np.random.uniform(0.6, 0.8, N_AREAS)
        return predicted_load, predicted_elasticity, base_price


class Layer4_MQTTEdgeMock:
    """Mock MQTT：将决策核心的指令下发给边缘节点"""

    @staticmethod
    def dispatch_commands(current_hour, r_opt, y_opt):
        print(f"[层4 - MQTT执行] 正在向 {N_AREAS} 个区域边缘计算节点下发滚动控制指令...")
        # 实际开发中： client.publish("v2g/area_01/cmd", payload)

        # 仅打印前3个区域的指令作为日志演示
        for area_id in range(3):
            price_adj_pct = r_opt[area_id] * 100
            discharge_kwh = y_opt[area_id]
            print(
                f"   => [充电站 {area_id:03d}] 指令A: 电价调整 {price_adj_pct:+.1f}% | 指令B: 目标放电 {discharge_kwh:.2f} kWh")


# ==========================================
# ⚙️ 阶段一：云端宏观规划引擎 (核心业务流)
# ==========================================

class CloudDecisionEngine:
    def __init__(self):
        self.db = Layer1_DatabaseMock()
        self.ai_service = Layer2_AIModelMock()
        self.mqtt = Layer4_MQTTEdgeMock()

    def run_stage_one_dispatch(self, current_hour):
        """执行流程图中的：阶段一：云端宏观规划（1小时级调度）"""
        print("\n" + "=" * 60)
        print(f"🕒 触发系统时间: {current_hour}:00 | 开始阶段一：云端宏观规划")
        print("=" * 60)

        # 1. 获取历史数据
        history = self.db.get_historical_data(current_hour)

        # 2. 调用预测层
        pred_L, pred_E, pred_C = self.ai_service.predict_next_hour(history, current_hour)

        # 3. 构建运筹调度环境并寻优 (层3)
        print(f"[层3 - 决策引擎] 启动多目标 VAE-WS-ADMM 优化器寻找帕累托最优解...")
        start_time = time.time()
        env = V2GEnvironment(pred_L, pred_E, pred_C, GRID_PRICE)
        r_opt, y_opt = bayesian_tune_vae_admm(env, trials=BAYESIAN_TRIALS)
        print(f"[层3 - 决策引擎] 优化计算完成，耗时: {time.time() - start_time:.2f} 秒")

        # 4. 指令解析与下发 (层4)
        self.mqtt.dispatch_commands(current_hour, r_opt, y_opt)

        print("-" * 60)
        print(f"✅ {current_hour}:00 调度指令下发完毕。边缘端将开始 5 分钟级滚动追踪 (阶段二)。")


# ==========================================
# 🚀 平台启动入口 (模拟时间流逝)
# ==========================================
if __name__ == '__main__':
    engine = CloudDecisionEngine()

    # 模拟系统按照时钟运行 (例如从 8:00 到 10:00)
    for hour in [8, 9, 10]:
        engine.run_stage_one_dispatch(current_hour=hour)
        time.sleep(1)  # 模拟等待进入下一个调度周期