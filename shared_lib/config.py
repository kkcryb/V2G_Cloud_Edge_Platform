# 全局参数配置文件
import os


class GlobalConfig:
    """V2G 云边协同平台全局配置中心"""

    # ==========================================
    # 🌍 全局系统开关与基础设定
    # ==========================================
    # 是否开启全流程单机闭环仿真（True: 本地模块互调跳过真实HTTP; False: 生产环境微服务请求）
    SIMULATION_MODE = True  #
    N_AREAS = 275  # 区域/节点数量（基于 UrbanEV 数据集）
    SEED = 50  # 全局随机种子，确保实验可复现

    # ==========================================
    # 📡 1. 物联网通信-数据感知层 (Data Hub)
    # ==========================================
    # InfluxDB 配置
    INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")  #
    INFLUX_TOKEN = os.getenv("INFLUX_TOKEN",
                             "CsD_NxHw34w2ta4ztFWJw8v0xb4V3tr4kVCMqU5PbWwWQf_6MzktxMOYHrZMJloVp4x5eUT_JBl-_ntZTf1xOw==")  #
    INFLUX_ORG = "my-org"  #
    INFLUX_BUCKET_RAW = "raw_data"  #
    INFLUX_BUCKET_AGG = "agg_data"  #

    # MQTT 消息队列配置 (解决IP冲突，统一使用此配置)
    MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
    MQTT_PORT = 1883  #
    MQTT_KEEPALIVE = 60  #

    # 主题统一定义
    TOPIC_EDGE_TO_CLOUD = "/v2g/simulation/uplink"  # 边端上报实际功率与SOC
    TOPIC_CLOUD_SCHEDULE = "v2g/cloud/schedule"  # 云端下发1小时级调度指令
    TOPIC_CLOUD_CONTROL = "/v2g/cloud/control"  # 云端下发即时启停控制指令

    # ==========================================
    # 🧠 2. AI预测推理层 (AI Service)
    # ==========================================
    # GCN-LSTM 模型参数定义
    NUM_NODES = N_AREAS  # 保持与系统节点数一致
    INPUT_DIM = 5  # 输入特征维度
    HIDDEN_DIM = 64  # 隐藏层维度
    SEQ_LEN = 24  # 历史序列长度（过去24小时）
    PRE_LEN = 24  # 预测未来长度（未来24小时）
    MODEL_WEIGHTS_PATH = os.getenv("MODEL_PATH", "./checkpoints/best_model.pth")  #
    # 微观弹性扰动参数
    PRICE_PERTURBATION_RATIO = 0.01  # 价格扰动比例 1%
    PRICE_FEATURE_INDEX = 1  # 电价在5维特征中的列索引

    # ==========================================
    # ⚙️ 3. 运筹调度引擎 (Optimization)
    # ==========================================
    ELASTICITY_RANGE = (-0.7, 1.1)  # 价格弹性系数范围
    GRID_PRICE = 0.7  # 电网侧基准电价（买电成本）

    # VAE-WS-ADMM 算法超参数
    ADMM_MAX_ITER = 30  # ADMM最大迭代次数
    VAE_EPOCHS = 5  # VAE微调训练轮数
    Y_MAX_RATIO = 0.15  # 最大放电量占总负荷的安全比例限制
    BAYESIAN_TRIALS = 15  # 贝叶斯寻优尝试次数

    # ==========================================
    # ⚡ 4. 边端控制与大屏展示 (Edge & Frontend)
    # ==========================================
    # 边端微观控制参数
    MAX_DISCHARGE_POWER = 60.0  # 充电桩最大物理放电功率 (kW)
    STEP_INTERVAL = 300  # 5分钟级微观控制步长 (单位：秒)
    MACRO_INTERVAL = 3600  # 云端1小时级宏观规划步长 (单位：秒)

    # 大屏 WebSocket 设定
    WS_HOST = "0.0.0.0"  #
    WS_PORT = 8081  #
    WS_PATH = "/ws/stream"  #
    WS_PUSH_INTERVAL = 5  # 推送真实频率到前端大屏的间隔 (秒)


config = GlobalConfig()