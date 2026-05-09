import asyncio
import json
from datetime import datetime

import numpy as np
import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from shared_lib.config import config
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ==========================================
# InfluxDB 初始化 (复用 shared_lib 全局配置)
# ==========================================
influx_client = InfluxDBClient(
    url=config.INFLUX_URL,
    token=config.INFLUX_TOKEN,
    org=config.INFLUX_ORG
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# ==========================================
# FastAPI
# ==========================================
app = FastAPI()

app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

@app.get("/")
async def get_index():
    with open("dist/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# ==========================================
# 全局状态字典与队列
# ==========================================
connected_websockets = []
edge_node_powers = {}
actual_curve = []

# ==========================================
# MQTT DataHub 回调
# ==========================================
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Dashboard MQTT 已连接")
        client.subscribe(config.TOPIC_EDGE_TO_CLOUD)
    else:
        print(f"MQTT连接失败: {rc}")

def on_message(client, userdata, msg):
    global edge_node_powers
    try:
        payload = json.loads(msg.payload.decode())
        node_id = str(payload["node_id"])
        actual_power = float(payload["actual_power_kw"])
        edge_node_powers[node_id] = actual_power
    except Exception as e:
        print("MQTT解析失败:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# ==========================================
# WebSocket 路由与广播
# ==========================================
@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    print("Dashboard 已连接")
    try:
        while True:
            await websocket.receive_text()
    except:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
        print("Dashboard 断开连接")

async def broadcast(data):
    disconnected = []
    for ws in connected_websockets:
        try:
            await ws.send_json(data)
        except:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in connected_websockets:
            connected_websockets.remove(ws)

# ==========================================
# 数据底座写入逻辑
# ==========================================
def write_to_influxdb(timestamp, total_load, node_details):
    try:
        point_total = (
            Point("platform_actual_load")
            .tag("source", "edge_simulation")
            .field("total_kw", float(total_load))
            .time(timestamp, WritePrecision.NS)
        )
        # 写入 config 中指定的聚合数据桶
        write_api.write(bucket=config.INFLUX_BUCKET_AGG, record=point_total)
    except Exception as e:
        print(f"InfluxDB 写入失败: {e}")

# ==========================================
# 云边协同主循环
# ==========================================
async def run_simulation_loop():
    print("云边协同系统启动")
    await asyncio.sleep(5)

    while True:
        # ==================================
        # 新1小时调度周期
        # ==================================
        actual_curve.clear()

        # AI预测基线与目标 (本地随机模拟)
        baseline_curve = np.random.normal(18000, 1500, 12)
        target_curve = baseline_curve * np.random.uniform(0.82, 0.92)

        baseline_curve = baseline_curve.tolist()
        target_curve = target_curve.tolist()

        print("\n云端完成新一轮1小时优化")

        # ==================================
        # 向区域节点下发调度任务
        # ==================================
        for node_id in range(config.N_AREAS):
            regional_target = float(target_curve[0] / config.N_AREAS)
            payload = {
                "node_id": str(node_id),
                "power_set": regional_target,
                "price_adj_rate": float(np.random.uniform(-0.15, 0.15)),
                "duration": 3600
            }
            mqtt_client.publish(config.TOPIC_CLOUD_SCHEDULE, json.dumps(payload))

        print("云端调度已下发")

        # 推送云端规划到前端
        await broadcast({
            "event_type": "CLOUD_DISPATCH_1H",
            "payload": {
                "baseline": baseline_curve,
                "target": target_curve
            }
        })

        # ==================================
        # 5分钟滚动追踪
        # ==================================
        for step in range(12):
            await asyncio.sleep(2)

            total_actual_load = round(sum(edge_node_powers.values()), 2)
            actual_curve.append([step, total_actual_load])

            print(f"Step={step} 聚合实际负荷={total_actual_load} kW")

            # 推送微观执行结果给前端
            await broadcast({
                "event_type": "EDGE_MICRO_UPDATE_5MIN",
                "payload": {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "step": step,
                    "actual_load": total_actual_load,
                    "actual_curve": actual_curve,
                    "active_nodes": len(edge_node_powers)
                }
            })

            # 闭环核心：将真实数据写入底座，为下一轮 AI 推理做准备
            write_to_influxdb(
                timestamp=datetime.now(),
                total_load=total_actual_load,
                node_details=edge_node_powers
            )

        print("当前1小时滚动周期结束，真实数据已入库，准备生成下一小时 AI 预测！")

# ==========================================
# 启动与生命周期管理
# ==========================================
@app.on_event("startup")
async def startup_event():
    mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    mqtt_client.loop_start()
    print("MQTT DataHub 已启动")
    asyncio.create_task(run_simulation_loop())

if __name__ == "__main__":
    uvicorn.run("run_system:app", host="127.0.0.1", port=8000, reload=False)