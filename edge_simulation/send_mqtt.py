import paho.mqtt.client as mqtt
import json
import time
import random

# 1. 配置 MQTT 连接参数
MQTT_BROKER = "10.212.241.132"
MQTT_PORT = 1883
TOPIC = "/v2g/simulation/uplink"


def run_mock_node():
    # 兼容你环境的稳定写法
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print("✅ [边缘节点] 连接 MQTT 成功，开始连续发送 1 分钟数据...")
    except Exception as e:
        print("❌ 连接失败：", e)
        return

    # 发送 1 分钟 = 60 秒，每 2 秒一条，共 30 条
    total_duration = 60
    interval = 2
    total_count = total_duration // interval

    for i in range(1, total_count + 1):
        # 生成假数据
        fake_power = round(random.uniform(30.0, 60.0), 1)
        fake_soc = round(0.40 + (i * 0.002), 2)

        payload = {
            "node_id": "HBUT_Station_001",
            "actual_power_kw": fake_power,
            "current_soc": fake_soc
        }

        # 发送
        client.publish(TOPIC, json.dumps(payload))
        print(f"🔼 第 {i}/{total_count} 条 | 功率: {fake_power}kW | SOC: {fake_soc * 100}%")

        time.sleep(interval)

    client.disconnect()
    print("\n🎉 [发送完成] 1 分钟数据全部发送成功！")


if __name__ == "__main__":
    run_mock_node()