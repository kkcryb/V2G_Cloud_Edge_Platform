import os
import sys
import asyncio
import json
from datetime import datetime
import pandas as pd
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
# 将项目根目录加入环境变量，以便跨目录导入运筹优化微服务
# ==========================================
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 🚨 核心修复：直接导入你写的 AI 预测模块与 VAE-WS-ADMM 运筹优化核心！
try:
    from optimization.main import (
        Layer2_AIDataAdapter,
        V2GEnvironment,
        bayesian_tune_vae_admm,
        BAYESIAN_TRIALS,
        GRID_PRICE
    )

    ai_service = Layer2_AIDataAdapter()
    print("成功挂载 AI预测与 VAE-WS-ADMM 运筹优化核心")
except ImportError as e:
    print(f"无法导入运筹优化核心，请检查路径: {e}")
    sys.exit(1)

# ==========================================
# InfluxDB 初始化
# ==========================================
influx_client = InfluxDBClient(
    url=config.INFLUX_URL,
    token=config.INFLUX_TOKEN,
    org=config.INFLUX_ORG
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# ==========================================
# FastAPI 与状态定义
# ==========================================
app = FastAPI()
app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")


@app.get("/")
async def get_index():
    with open("dist/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


connected_websockets = []
edge_node_powers = {}
actual_curve = []

# ==========================================
# MQTT DataHub 回调
# ==========================================
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Dashboard MQTT 已连接，正在监听边缘集群...")
        client.subscribe(config.TOPIC_EDGE_TO_CLOUD)


def on_message(client, userdata, msg):
    global edge_node_powers
    try:
        payload = json.loads(msg.payload.decode())
        node_id = str(payload["node_id"])
        edge_node_powers[node_id] = float(payload["actual_power_kw"])
    except Exception:
        pass


mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)


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


def write_to_influxdb(timestamp, total_load, node_details):
    try:
        point_total = (
            Point("platform_actual_load")
            .tag("source", "edge_simulation")
            .field("total_kw", float(total_load))
            .time(timestamp, WritePrecision.NS)
        )
        write_api.write(bucket=config.INFLUX_BUCKET_AGG, record=point_total)
    except Exception as e:
        print(f"InfluxDB 写入失败: {e}")


# ==========================================
# 云边协同主循环 (真正由 AI 和 运筹算法驱动)
# ==========================================
async def run_simulation_loop():
    print("云边协同系统启动，等待首次运筹调度计算...")
    await asyncio.sleep(2)

    hour_counter = 8  # 从早上8点开始仿真

    while True:
        actual_curve.clear()

        print(f"\n[第 {hour_counter}:00 时] 启动 AI大脑 与 运筹优化引擎...")

        # 🚨 1. 真实AI大脑：提取真实基准负荷 (pred_L) 和 真实价格弹性系数 (pred_E)
        pred_L, pred_E, pred_C = ai_service.predict_next_hour(history_data=None, current_hour=hour_counter)

        # 🚨 2. 真实运筹核心：使用 VAE-WS-ADMM 求解 275个节点的帕累托最优指令
        env = V2GEnvironment(pred_L, pred_E, pred_C, GRID_PRICE)
        r_opt, y_opt = bayesian_tune_vae_admm(env, trials=BAYESIAN_TRIALS)

        # 🚨 3. 数学严谨对齐：计算全网预测基线与优化目标
        total_base_load = round(sum(pred_L), 2)

        # 目标负荷 = 基础负荷 * (1 + 弹性系数 * 最优调价) - 最优放电量
        opt_loads = pred_L * (1 + pred_E * r_opt) - y_opt
        total_target_load = round(sum(opt_loads), 2)

        # 构建给前端展示的12步长曲线 (引入极小的微波动让图表不至于变成死板的平线)
        baseline_curve = [round(total_base_load * np.random.uniform(0.99, 1.01), 2) for _ in range(12)]
        target_curve = [round(total_target_load * np.random.uniform(0.99, 1.01), 2) for _ in range(12)]

        print(f"云端规划完成 | 全网真实基准: {total_base_load} kW | 运筹削峰目标: {total_target_load} kW")

        # 🚨 4. 下发 运筹引擎算出的专属指令 到边缘节点
        for i in range(config.N_AREAS):
            payload = {
                "node_id": str(i),
                "power_set": round(float(y_opt[i]), 2),  # VAE-WS-ADMM 算出的最优放电量
                "price_adj_rate": round(float(r_opt[i]), 4),  # VAE-WS-ADMM 算出的最优调价比例
                "base_load": float(pred_L[i]),  # AI 提取的当前真实自然负荷
                "duration": 3600
            }
            mqtt_client.publish(config.TOPIC_CLOUD_SCHEDULE, json.dumps(payload))

        await broadcast({
            "event_type": "CLOUD_DISPATCH_1H",
            "payload": {
                "baseline": baseline_curve,
                "target": target_curve
            }
        })

        # 等待 MQTT 指令下发完成
        await asyncio.sleep(3)

        # 5. 5分钟滚动追踪闭环
        for step in range(12):
            await asyncio.sleep(2.5)

            total_actual_load = round(sum(edge_node_powers.values()), 2)
            actual_curve.append([step, total_actual_load])

            print(f"Step={step} 聚合实际负荷={total_actual_load} kW (活跃节点:{len(edge_node_powers)})")

            await broadcast({
                "event_type": "EDGE_MICRO_UPDATE_5MIN",
                "payload": {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "step": step,
                    "actual_load": total_actual_load,
                    "actual_curve": actual_curve,
                    "active_nodes": len(edge_node_powers),
                    "node_details": edge_node_powers
                }
            })

            write_to_influxdb(datetime.now(), total_actual_load, edge_node_powers)

        print(f"第 {hour_counter}:00 时滚动结束，准备进入下一调度周期。")
        hour_counter += 1


@app.on_event("startup")
async def startup_event():
    mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    mqtt_client.loop_start()
    asyncio.create_task(run_simulation_loop())


if __name__ == "__main__":
    uvicorn.run("run_system:app", host="127.0.0.1", port=8000, reload=False)
