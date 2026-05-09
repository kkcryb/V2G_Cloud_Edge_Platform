import os
import sys
import time
import json
import warnings
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from scipy.optimize import minimize

warnings.filterwarnings('ignore')

# ==========================================
# 🎯 将项目根目录加入环境变量，引入全局配置
# ==========================================
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from shared_lib.config import config

# 从配置中读取全局参数
SEED = getattr(config, 'SEED', 50)
N_AREAS = getattr(config, 'N_AREAS', 275)
ELASTICITY_RANGE = getattr(config, 'ELASTICITY_RANGE', (-0.7, 1.1))
GRID_PRICE = getattr(config, 'GRID_PRICE', 0.7)

ADMM_MAX_ITER = getattr(config, 'ADMM_MAX_ITER', 30)
VAE_EPOCHS = getattr(config, 'VAE_EPOCHS', 5)
Y_MAX_RATIO = getattr(config, 'Y_MAX_RATIO', 0.15)
BAYESIAN_TRIALS = getattr(config, 'BAYESIAN_TRIALS', 15)


# ==========================================
# 🧬 【核心网络】条件变分自编码器 (CVAE)
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
# 🔥 【深度融合内核】VAE 热启动 + 数学精确求解
# ==========================================
class V2GEnvironment:
    def __init__(self, L_base, elasticity, C_price, C_grid):
        self.L_base = L_base
        self.elasticity = elasticity
        self.C_price = C_price
        self.C_grid = C_grid
        self.n_areas = len(L_base)
        self.r_limit = [-0.8, 1.2]
        # 🚨 防止 y_limit 的上限是 0 或 NaN
        max_l = np.max(L_base)
        self.y_limit = [0, max_l * Y_MAX_RATIO if max_l > 0 else 10.0]
        self.y_max_arr = np.full(self.n_areas, self.y_limit[1])

    def evaluate(self, r, y):
        r = np.clip(r, self.r_limit[0], self.r_limit[1])
        y = np.clip(y, self.y_limit[0], self.y_limit[1])
        L_opt = self.L_base * (1 + self.elasticity * r) - y
        f1_std = np.std(L_opt)
        f2_rev = np.sum(self.C_price * (1 + r) * (self.L_base * (1 + self.elasticity * r)) + self.C_grid * y)
        return f1_std, f2_rev, L_opt


def run_vae_ws_admm(env, w1, w2, rho_init, max_iter=30):
    rho = rho_init
    lam = np.zeros(env.n_areas)
    alpha, z_hat = 1.0, env.L_base.copy()
    z, l_val = env.L_base.copy(), env.L_base.copy()
    r_opt_exact, y_opt_exact = np.zeros(env.n_areas), np.zeros(env.n_areas)

    vae_agent = V2G_CVAE()
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


def bayesian_tune_vae_admm(env, trials=5):
    import optuna
    def objective(trial):
        w1 = trial.suggest_float('w1', 10, 5000, log=True)
        w2 = trial.suggest_float('w2', 0.1, 20)
        rho = trial.suggest_float('rho_init', 0.5, 10)

        r, y = run_vae_ws_admm(env, w1, w2, rho, max_iter=5)
        f1, f2, _ = env.evaluate(r, y)

        # 🚨 核心修复1：防止标准差等于 0 导致 /0 计算变成 NaN
        std_base = np.std(env.L_base)
        if std_base < 1e-6:
            std_base = 1e-6

        norm_f1 = f1 / std_base
        norm_f2 = 1 - (f2 / 10000)

        result = np.sqrt(norm_f1 ** 2 + norm_f2 ** 2)

        # 🚨 核心修复2：如果因不可抗力依旧算出了 NaN，强制返回极大惩罚值，让 Optuna 避开这组参数
        if np.isnan(result):
            return 999999.0

        return result

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    best_param = study.best_params
    r, y = run_vae_ws_admm(env, **best_param, max_iter=ADMM_MAX_ITER)
    return r, y


# ==========================================
# 🔌 真实系统对接层 (AI预测适配器)
# ==========================================
class Layer2_AIDataAdapter:
    """直接接入深圳 UrbanEV 真实数据集"""

    def __init__(self):
        base_path = os.path.join(project_root, 'ai_prediction', 'training', 'data')
        self.volume_csv = os.path.join(base_path, 'volume.csv')
        self.price_csv = os.path.join(base_path, 'e_price.csv')
        self.df_volume = None
        self.df_price = None

        try:
            v_df = pd.read_csv(self.volume_csv)
            self.df_volume = v_df.select_dtypes(include=['number'])

            p_df = pd.read_csv(self.price_csv)
            self.df_price = p_df.select_dtypes(include=['number'])
            print(f"✅ 成功加载 UrbanEV 真实数据集节点特征！")
        except Exception as e:
            print(f"⚠️ 无法读取真实数据集: {e}")

    def predict_next_hour(self, history_data=None, current_hour=8):
        print(f"[层2 - AI大脑] 提取 {current_hour}:00 的真实基准负荷与电价...")

        # 🚨 核心修复3：安全提取负荷，防止数据列不足或空数据引发切片异常
        if self.df_volume is not None and not self.df_volume.empty:
            row_idx = current_hour % len(self.df_volume)
            pred_L = self.df_volume.iloc[row_idx].values[:N_AREAS].astype(float)

            # 如果提取出来的列数不足 N_AREAS（例如CSV数据被损坏），使用平均值补齐
            if len(pred_L) < N_AREAS:
                pred_L = np.pad(pred_L, (0, N_AREAS - len(pred_L)), 'mean')

            pred_L = np.nan_to_num(pred_L, nan=30.0)
            pred_L = np.clip(pred_L, 5.0, 2000.0)  # 剔除极值
        else:
            # 极低概率失败时的安全后备
            pred_L = np.random.normal(50, 10, N_AREAS)

        if self.df_price is not None and not self.df_price.empty:
            row_idx = current_hour % len(self.df_price)
            pred_C = self.df_price.iloc[row_idx].values[:N_AREAS].astype(float)
            if len(pred_C) < N_AREAS:
                pred_C = np.pad(pred_C, (0, N_AREAS - len(pred_C)), 'mean')
            pred_C = np.nan_to_num(pred_C, nan=GRID_PRICE)
        else:
            pred_C = np.full(N_AREAS, GRID_PRICE)

        # 价格弹性分布模拟
        np.random.seed(current_hour + 42)
        pred_E = np.random.uniform(ELASTICITY_RANGE[0], ELASTICITY_RANGE[1], N_AREAS)

        return pred_L, pred_E, pred_C


if __name__ == "__main__":
    adapter = Layer2_AIDataAdapter()
    pred_L, pred_E, pred_C = adapter.predict_next_hour(current_hour=8)
    env = V2GEnvironment(pred_L, pred_E, pred_C, GRID_PRICE)
    print("开始运筹测试寻优...")
    r_opt, y_opt = bayesian_tune_vae_admm(env, trials=2)
    print(f"寻优完成，前3个节点的放电量: {y_opt[:3]}")