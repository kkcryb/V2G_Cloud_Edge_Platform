# edge_simulation/main.py
import time
import json
import random
import threading
import paho.mqtt.client as mqtt

# 引入全局统一配置
from shared_lib.config import config


# ==========================================
# 🧠 边端微观控制器 (保留你原有的算法，增加节点ID标识)
# ==========================================
class EdgeController:
    def __init__(self, node_id):
        self.node_id = node_id
        self.target_kwh = 0.0
        self.finished_kwh = 0.0
        self.remain_step = 0
        self.current_price_adj = 0.0
        self.is_running = False

    def set_task(self, target_kw, price_adj_rate, duration_sec):
        """接收阶段一下发的一小时宏观目标"""
        # 注意：云端下发的是功率(kW)，我们在这里转化为总目标能量(kWh)
        # 例如: 1小时放电 60kW，其实就是放电 60kWh
        self.target_kwh = target_kw * (duration_sec / 3600.0)
        self.current_price_adj = price_adj_rate
        self.finished_kwh = 0.0
        self.remain_step = int(duration_sec / config.STEP_INTERVAL)  # 3600/300 = 12步
        self.is_running = True
        print(f"[{self.node_id}] 🎯 锁定宏观目标: {self.target_kwh:.2f} kWh, 拆分为 {self.remain_step} 个控制周期.")

    def run_step(self, current_load):
        """执行阶段二：5分钟级滚动微观控制"""
        if self.remain_step <= 0:
            self.is_running = False
            return 0.0, 0.0

        # 微观调节逻辑：平摊剩余目标
        p_theory = (self.target_kwh - self.finished_kwh) / (self.remain_step * (config.STEP_INTERVAL / 3600.0))
        # 物理限制约束
        p_actual = min(p_theory, config.MAX_DISCHARGE_POWER, current_load)
        kwh = p_actual * (config.STEP_INTERVAL / 3600.0)

        self.finished_kwh += kwh
        self.remain_step -= 1

        return round(p_actual, 2), round(kwh, 2)


# ==========================================
# 🌐 边缘节点守护进程 (网关代理)
# ==========================================
class EdgeGatewayDaemon:
    def __init__(self, simulate_node_id="0"):
        self.node_id = simulate_node_id
        self.controller = EdgeController(self.node_id)

        # 初始化 MQTT
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ [Edge-{self.node_id}] 成功连接到云端 MQTT Broker")
            # 订阅云端调度指令
            self.client.subscribe(config.TOPIC_CLOUD_SCHEDULE)
        else:
            print(f"❌ [Edge-{self.node_id}] MQTT连接失败，错误码：{rc}")

    def on_message(self, client, userdata, msg):
        """阶段二入口：收到阶段一下发的宏观规划指令"""
        if msg.topic == config.TOPIC_CLOUD_SCHEDULE:
            try:
                payload = json.loads(msg.payload.decode('utf-8'))

                # 判断是不是发给自己的指令 (为简化仿真，只要收到就执行)
                # 实际中应增加 if str(payload["node_id"]) == self.node_id:

                print(f"\n📥 [Edge-{self.node_id}] 收到云端宏观调度指令:")
                target_power = payload.get("power_set", 0.0)
                price_adj = payload.get("price_adj_rate", 0.0)
                duration = payload.get("duration", 3600)

                # 将目标交给控制器
                self.controller.set_task(target_power, price_adj, duration)

            except Exception as e:
                print(f"⚠️ 指令解析异常: {e}")

    def report_status_to_cloud(self, actual_power, kwh):
        """阶段三：将执行结果通过 MQTT 回写到云端数据中台"""
        # 模拟设备当前的 SOC (简单粗略模拟)
        soc = round(0.5 - (self.controller.finished_kwh / 100.0), 2)

        payload = {
            "node_id": self.node_id,
            "actual_power_kw": actual_power,
            "current_soc": max(soc, 0.1)  # 保护下限
        }
        self.client.publish(config.TOPIC_EDGE_TO_CLOUD, json.dumps(payload))
        print(
            f"🔼 [上报云端] 瞬时功率: {actual_power}kW | 本次放电: {kwh}kWh | 目标完成度: {self.controller.finished_kwh:.2f}/{self.controller.target_kwh:.2f} kWh")

    def run_control_loop(self):
        """这是独立线程：永远每隔 5 分钟 (为测试缩短为 5 秒) 执行一次检查"""
        while True:
            if self.controller.is_running:
                # 模拟当前站点的实际可控负荷
                current_load = round(random.uniform(30.0, 80.0), 2)

                # 滚动寻优
                actual_power, kwh = self.controller.run_step(current_load)

                # 结果回传
                self.report_status_to_cloud(actual_power, kwh)

                if self.controller.remain_step <= 0:
                    print(f"✅ [Edge-{self.node_id}] 本小时控制周期结束，等待云端新指令...")

            # config.STEP_INTERVAL 是 300秒。
            # 为了能在单机快速跑出效果，开启 SIMULATION_MODE 时改为 2秒
            sleep_time = 2 if config.SIMULATION_MODE else config.STEP_INTERVAL
            time.sleep(sleep_time)

    def start(self):
        print(f"🚀 边缘计算节点 [Node-{self.node_id}] 守护进程启动...")
        try:
            self.client.connect(config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE)
            self.client.loop_start()

            # 启动微观调控独立线程
            control_thread = threading.Thread(target=self.run_control_loop, daemon=True)
            control_thread.start()

            # 保持主线程存活
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 边缘节点关闭")
            self.client.loop_stop()
            self.client.disconnect()


if __name__ == "__main__":
    # 模拟启动 0号 节点
    gateway = EdgeGatewayDaemon(simulate_node_id="0")
    gateway.start()