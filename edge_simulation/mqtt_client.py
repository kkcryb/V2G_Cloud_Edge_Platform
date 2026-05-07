import paho.mqtt.client as mqtt
from config import MQTT_BROKER, MQTT_PORT, SUB_TOPIC, PUB_TOPIC

# 全局MQTT客户端实例
client = mqtt.Client(client_id="edge_controller")

# 回调函数：连接成功时触发
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT服务器连接成功")
        client.subscribe(SUB_TOPIC)
        print(f"📡 已订阅指令主题：{SUB_TOPIC}")
    else:
        print(f"❌ MQTT连接失败，错误码：{rc}")

# 回调函数：收到消息时触发
def on_message(client, userdata, msg):
    print(f"\n📥 收到云端指令：{msg.payload.decode('utf-8')}")
    # 后期在这里解析JSON指令，调用controller.set_task()

# 绑定回调函数
client.on_connect = on_connect
client.on_message = on_message
