import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib
import json
import os
import optuna
import warnings
import torch
import torch.nn as nn
import torch.optim as optim
from scipy.optimize import minimize

warnings.filterwarnings('ignore')

# ==========================================
# 🎯 全局参数配置区
# ==========================================
SEED = 50
N_AREAS = 275
TIME_SLOTS = list(range(24))  # 24小时全时段

ELASTICITY_RANGE = (-0.7, 1.1)
GRID_PRICE = 0.7

ADMM_MAX_ITER = 30  # ADMM 外部协调迭代次数
VAE_EPOCHS = 5  # VAE 每次的自我模仿学习次数
Y_MAX_RATIO = 0.15
BAYESIAN_TRIALS = 15  # 贝叶斯搜索次数

# 绘图风格设置（中文显示）
plt.style.use('bmh')
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial']
matplotlib.rcParams['axes.unicode_minus'] = False

if not os.path.exists("./json"):
    os.makedirs("./json")


# ==========================================
# 🧬 【核心网络】条件变分自编码器 (CVAE)
# ==========================================
class V2G_CVAE(nn.Module):
    def __init__(self, input_dim=5, latent_dim=8):
        super(V2G_CVAE, self).__init__()
        # 编码器 (将电网状态特征压缩)
        self.enc = nn.Sequential(
            nn.Linear(input_dim, 32), nn.ReLU(),
            nn.Linear(32, 16), nn.ReLU()
        )
        self.fc_mu = nn.Linear(16, latent_dim)
        self.fc_logvar = nn.Linear(16, latent_dim)

        # 解码器 (解码为具体的 r 和 y 策略)
        self.dec = nn.Sequential(
            nn.Linear(latent_dim, 16), nn.ReLU(),
            nn.Linear(16, 32), nn.ReLU()
        )
        self.out_r = nn.Linear(32, 1)
        self.out_y = nn.Linear(32, 1)

    def encode(self, x):
        h = self.enc(x)
        return self.fc_mu(h), self.fc_logvar(h)

    def decode(self, z):
        h = self.dec(z)
        r_pred = torch.tanh(self.out_r(h)) * 1.0 + 0.2  # 映射到近 [-0.8, 1.2]
        y_pred = torch.sigmoid(self.out_y(h))  # 映射到 [0, 1] 比例
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
    rho = rho_init
    rho_min, rho_max = 0.1, 100.0
    mu_res, tau_incr, tau_decr = 10.0, 2.0, 2.0

    z = env.L_base.copy()
    z_prev = env.L_base.copy()
    l_val = env.L_base.copy()
    lam = np.zeros(env.n_areas)

    alpha = 1.0
    z_hat = z.copy()

    r_opt_exact = np.zeros(env.n_areas)
    y_opt_exact = np.zeros(env.n_areas)

    # 初始化 VAE 代理与优化器
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

        # =======================================================
        # 步骤 1: VAE 高速预测全局初始解 (Warm Start)
        # =======================================================
        vae_agent.eval()
        with torch.no_grad():
            r_pred_t, y_ratio_t, _, _ = vae_agent(features)
            r_pred = r_pred_t.squeeze().numpy()
            y_pred = (y_ratio_t * T_YMAX).squeeze().numpy()

        # =======================================================
        # 步骤 2: L-BFGS-B 数学求解器接力微调 (保障绝对精度)
        # =======================================================
        for i in range(env.n_areas):
            def local_obj(vars):
                r, y = vars
                l_i = env.L_base[i] * (1 + env.elasticity[i] * r) - y
                rev_i = env.C_price[i] * (1 + r) * env.L_base[i] * (1 + env.elasticity[i] * r) + env.C_grid * y
                return -w2 * rev_i + lam[i] * l_i + (rho / 2.0) * (l_i - z_hat[i]) ** 2

            bounds = [(env.r_limit[0], env.r_limit[1]), (env.y_limit[0], env.y_limit[1])]
            # ✨ 核心改进：以 VAE 的输出作为精确求解器的起点 x0
            x0 = [np.clip(r_pred[i], env.r_limit[0], env.r_limit[1]),
                  np.clip(y_pred[i], env.y_limit[0], env.y_limit[1])]

            res = minimize(local_obj, x0, bounds=bounds, method='L-BFGS-B', options={'maxiter': 10})
            r_opt_exact[i], y_opt_exact[i] = res.x
            l_val[i] = env.L_base[i] * (1 + env.elasticity[i] * r_opt_exact[i]) - y_opt_exact[i]

        # =======================================================
        # 步骤 3: VAE 自我模仿学习 (Solver-in-the-loop)
        # =======================================================
        target_r = torch.FloatTensor(r_opt_exact).unsqueeze(1)
        target_y_ratio = torch.FloatTensor(y_opt_exact / env.y_max_arr).unsqueeze(1)

        vae_agent.train()
        for _ in range(VAE_EPOCHS):
            optimizer.zero_grad()
            out_r, out_y_ratio, mu, logvar = vae_agent(features)
            # 让 VAE 学习数学求解器的绝对精确解 (Imitation Learning)
            recon_loss = nn.MSELoss()(out_r, target_r) + nn.MSELoss()(out_y_ratio, target_y_ratio)
            kld_loss = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
            loss = recon_loss + 0.01 * kld_loss
            loss.backward()
            optimizer.step()

        # =======================================================
        # 步骤 4: 云端协调 (z-update & lam-update)
        # =======================================================
        v = l_val + lam / rho
        v_mean = np.mean(v)
        z_new = (rho * v + 2 * w1 / env.n_areas * v_mean) / (rho + 2 * w1 / env.n_areas)

        alpha_new = (1 + np.sqrt(1 + 4 * alpha ** 2)) / 2.0
        z_hat = z_new + ((alpha - 1) / alpha_new) * (z_new - z)
        alpha = alpha_new
        z = z_new

        lam = lam + rho * (l_val - z_hat)

        res_pri = np.linalg.norm(l_val - z)
        res_dual = np.linalg.norm(-rho * (z - z_prev))
        if res_pri > mu_res * res_dual:
            rho = min(rho * tau_incr, rho_max)
        elif res_dual > mu_res * res_pri:
            rho = max(rho / tau_decr, rho_min)
        z_prev = z.copy()

    return r_opt_exact, y_opt_exact


def bayesian_tune_vae_admm(env, trials=10):
    history_f1, history_f2 = [], []
    best_param = None

    def objective(trial):
        w1 = trial.suggest_float('w1', 10, 5000, log=True)
        w2 = trial.suggest_float('w2', 0.1, 20)
        rho = trial.suggest_float('rho_init', 0.5, 10)

        r, y = run_vae_ws_admm(env, w1, w2, rho, max_iter=15)
        f1, f2, _ = env.evaluate(r, y)

        history_f1.append(f1)
        history_f2.append(f2)

        norm_f1 = f1 / np.std(env.L_base)
        norm_f2 = 1 - (f2 / np.max(history_f2) if len(history_f2) > 1 else 1)
        return np.sqrt(norm_f1 ** 2 + norm_f2 ** 2)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=trials, show_progress_bar=False)

    best_param = study.best_params
    r, y = run_vae_ws_admm(env, **best_param, max_iter=ADMM_MAX_ITER)
    f1, f2, L_opt = env.evaluate(r, y)
    return r, y, L_opt, f1, f2, best_param, history_f1, history_f2


# ==========================================
# 24 小时动态数据生成
# ==========================================
np.random.seed(SEED)
L_ori, C_price_dict = {}, {}

for t in TIME_SLOTS:
    if 0 <= t <= 6:
        mean, std, p_min, p_max = 60, 5, 0.3, 0.4
    elif 7 <= t <= 10:
        mean, std, p_min, p_max = 110, 8, 0.6, 0.8
    elif 11 <= t <= 16:
        mean, std, p_min, p_max = 90, 7, 0.5, 0.6
    elif 17 <= t <= 21:
        mean, std, p_min, p_max = 145, 10, 0.8, 1.2
    else:
        mean, std, p_min, p_max = 80, 6, 0.4, 0.5

    L_ori[t] = np.random.normal(mean, std, N_AREAS)
    C_price_dict[t] = np.random.uniform(p_min, p_max, N_AREAS)

elasticity = np.random.uniform(ELASTICITY_RANGE[0], ELASTICITY_RANGE[1], N_AREAS)

# ==========================================
# 🚀 执行优化 (VAE-WS-ADMM)
# ==========================================
results = {}
print("=" * 80)
print("🚀 启动 [VAE 代理热启动 + 数学绝对精度求解] 联合博弈框架...")
print("=" * 80)

for t in TIME_SLOTS:
    print(f"⏳ 正在执行 {t:02d}:00 时段高精度调度...")
    env = V2GEnvironment(L_ori[t], elasticity, C_price_dict[t], GRID_PRICE)
    r_opt, y_opt, l_opt, f1_opt, f2_opt, params, hf1, hf2 = bayesian_tune_vae_admm(env, trials=BAYESIAN_TRIALS)

    results[t] = {
        'L_base': L_ori[t], 'L_opt': l_opt, 'f1_base': np.std(L_ori[t]), 'f1_opt': f1_opt,
        'f2_base': np.sum(C_price_dict[t] * L_ori[t]), 'f2_opt': f2_opt,
        'best_params': params, 'history_f1': hf1, 'history_f2': hf2
    }

# ==========================================
# 📊 打印与绘图
# ==========================================
print("\n" + "=" * 80)
print("                   24 小时全时段目标函数改善汇总")
print("=" * 80)
for t in TIME_SLOTS:
    res = results[t]
    print(
        f"📅 {t:02d}:00 | F1 下降: {(res['f1_base'] - res['f1_opt']) / res['f1_base'] * 100:>6.2f}% | F2 提升: {(res['f2_opt'] - res['f2_base']) / res['f2_base'] * 100:>6.2f}%")

PLOT_TIMES = [4, 9, 14, 19]
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('基于 VAE-WS-ADMM 的代表性时段高精度负荷调度', fontsize=18, fontweight='bold', y=0.96)
area_index = np.arange(N_AREAS)

for idx, t in enumerate(PLOT_TIMES):
    ax = axes[idx // 2, idx % 2]
    ax.plot(area_index, L_ori[t], linestyle='--', color='#1f77b4', label='优化前无序负荷')
    ax.plot(area_index, results[t]['L_opt'], linewidth=2.5, color='#d62728', label='高精度优化后负荷')
    ax.set_title(f'{t:02d}:00 典型时段')
    ax.set_xlabel('区域节点编号')
    ax.set_ylabel('等效总负荷 (kW)')
    ax.legend()

plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig('load_comparison_VAE_WS_ADMM.png', dpi=300)
plt.show()

fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))
fig2.suptitle('24 小时优化前后多目标量化对比 (高精度版)', fontsize=18, fontweight='bold', y=0.96)
x_pos = np.arange(len(TIME_SLOTS))

ax1.bar(x_pos - 0.175, [results[t]['f1_base'] for t in TIME_SLOTS], 0.35, label='优化前', color='#1f77b4')
ax1.bar(x_pos + 0.175, [results[t]['f1_opt'] for t in TIME_SLOTS], 0.35, label='优化后', color='#d62728')
ax1.set_title('全天负荷平稳性 F1 (目标：越平缓越好)')
ax1.set_xticks(x_pos)
ax1.legend()

ax2.bar(x_pos - 0.175, [results[t]['f2_base'] for t in TIME_SLOTS], 0.35, label='优化前', color='#1f77b4')
ax2.bar(x_pos + 0.175, [results[t]['f2_opt'] for t in TIME_SLOTS], 0.35, label='优化后', color='#d62728')
ax2.set_title('全天系统综合经济收益 F2 (目标：越高越好)')
ax2.set_xticks(x_pos)
ax2.legend()

plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig('objective_comparison_24H_high_precision.png', dpi=300)
plt.show()