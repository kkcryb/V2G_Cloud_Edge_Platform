import time
import json
import random
import threading
import paho.mqtt.client as mqtt

from shared_lib.config import config


# ==========================================
# 🧠 边端微观控制器 (彻底基于真实负荷运行)
# ==========================================
class EdgeController:
    def __init__(self, node_id):
        self.node_id = node_id
        self.target_kwh = 0.0
        self.finished_kwh = 0.0
        self.remain_step = 0
        self.current_price_adj = 0.0
        self.is_running = False

        # 默认回退负荷
        self.base_load = 50.0

        # 模拟该节点用户的平均价格敏感度 (与云端弹性系数相呼应)
        self.local_elasticity = random.uniform(*config.ELASTICITY_RANGE)

    def set_task(self, target_kw, price_adj_rate, duration_sec, base_load):
        self.target_kwh = target_kw * (duration_sec / 3600.0)
        self.current_price_adj = price_adj_rate
        self.base_load = base_load  # 🚨 核心：接收云端传来的 UrbanEV 真实专属负荷

        self.finished_kwh = 0.0
        self.remain_step = int(duration_sec / config.STEP_INTERVAL)
        self.is_running = True

    def simulate_actual_load(self):
        """核心仿真逻辑：生成受电价影响的真实物理负荷"""
        # 1. 放弃假数据！基于真实的 base_load 加入细微的环境白噪声模拟5分钟波动
        current_step_base = self.base_load * random.uniform(0.96, 1.04)

        # 2. 核心！引入价格弹性：价格上涨 -> 负荷下降
        elastic_load = current_step_base * (1 + self.local_elasticity * self.current_price_adj)

        return max(elastic_load, 0.0)

    def run_step(self):
        if self.remain_step <= 0:
            self.is_running = False
            return self.simulate_actual_load(), 0.0, False

        # 1. 获取受价格影响后的当前真实网内负荷
        current_load = self.simulate_actual_load()

        # 2. V2G 放电追踪逻辑
        p_theory = (self.target_kwh - self.finished_kwh) / (self.remain_step * (config.STEP_INTERVAL / 3600.0))
        max_p = getattr(config, 'MAX_DISCHARGE_POWER', 60.0)
        p_actual = min(p_theory, max_p, current_load)

        kwh = p_actual * (config.STEP_INTERVAL / 3600.0)
        self.finished_kwh += kwh
        self.remain_step -= 1

        # 最终该节点的净功率 = 弹性负荷 - V2G反向放电
        net_power = current_load - p_actual

        return round(net_power, 2), round(kwh, 2), True


# ==========================================
# 🌐 边缘集群网关 (同时管理全网所有节点)
# ==========================================
class EdgeFleetSimulator:
    def __init__(self):
        self.controllers = {str(i): EdgeController(str(i)) for i in range(config.N_AREAS)}

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ [边缘集群] 成功连接Broker。共挂载 {config.N_AREAS} 个真实孪生节点。")
            self.client.subscribe(config.TOPIC_CLOUD_SCHEDULE)
        else:
            print(f"❌ MQTT连接失败，错误码：{rc}")

    def on_message(self, client, userdata, msg):
        """接收运筹层下发的真实群组调度指令"""
        if msg.topic == config.TOPIC_CLOUD_SCHEDULE:
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
                node_id = str(payload.get("node_id"))

                if node_id in self.controllers:
                    self.controllers[node_id].set_task(
                        target_kw=payload.get("power_set", 0.0),
                        price_adj_rate=payload.get("price_adj_rate", 0.0),
                        duration_sec=payload.get("duration", 3600),
                        base_load=payload.get("base_load", 50.0)  # 🚨 从云端接管真实的节点历史负荷
                    )
            except Exception as e:
                pass

    def run_fleet_control_loop(self):
        """独立线程：执行微观控制并回写数据"""
        while True:
            active_nodes = sum(1 for c in self.controllers.values() if c.is_running)

            if active_nodes > 0:
                for node_id, controller in self.controllers.items():
                    if not controller.is_running:
                        continue

                    # 1. 真实物理计算
                    net_power, kwh, _ = controller.run_step()

                    # 2. 模拟 SOC
                    soc = max(round(0.6 - (controller.finished_kwh / 50.0), 2), 0.1)

                    # 3. 回写数据到云端
                    payload = {
                        "node_id": node_id,
                        "actual_power_kw": net_power,
                        "current_soc": soc
                    }
                    self.client.publish(config.TOPIC_EDGE_TO_CLOUD, json.dumps(payload))

            # 🚨 修复时差问题：边端必须严格等待 2 秒并发送完，让云端 (2.5秒) 能够安全采集
            sleep_time = 2 if getattr(config, 'SIMULATION_MODE', True) else config.STEP_INTERVAL
            time.sleep(sleep_time)

    def start(self):
        print("🚀 启动 V2G 边缘集群物理并发引擎...")
        try:
            self.client.connect(config.MQTT_BROKER, config.MQTT_PORT, getattr(config, 'MQTT_KEEPALIVE', 60))
            self.client.loop_start()

            control_thread = threading.Thread(target=self.run_fleet_control_loop, daemon=True)
            control_thread.start()

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 边缘集群仿真结束")
            self.client.loop_stop()
            self.client.disconnect()


if __name__ == "__main__":
    fleet_simulator = EdgeFleetSimulator()
    fleet_simulator.start()