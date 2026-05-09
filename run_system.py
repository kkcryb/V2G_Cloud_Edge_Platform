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
from system_runner import GlobalOrchestrator

# ==========================================
# FastAPI
# ==========================================
app = FastAPI()

app.mount(
    "/assets",
    StaticFiles(directory="dist/assets"),
    name="assets"
)


@app.get("/")
async def get_index():
    with open(
        "dist/index.html",
        "r",
        encoding="utf-8"
    ) as f:
        return HTMLResponse(f.read())


# ==========================================
# WebSocket
# ==========================================
connected_websockets = []

# ==========================================
# MQTT DataHub
# ==========================================
mqtt_client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION1
)

# 保存所有区域节点实时功率
edge_node_powers = {}

# 聚合后的真实负荷曲线
actual_curve = []


# ==========================================
# MQTT 回调
# ==========================================
def on_connect(client, userdata, flags, rc):

    if rc == 0:

        print("✅ Dashboard MQTT 已连接")

        # 订阅边端回传
        client.subscribe(
            config.TOPIC_EDGE_TO_CLOUD
        )

    else:
        print(f"❌ MQTT连接失败: {rc}")


def on_message(client, userdata, msg):

    global edge_node_powers

    try:

        payload = json.loads(
            msg.payload.decode()
        )

        node_id = str(payload["node_id"])

        actual_power = float(
            payload["actual_power_kw"]
        )

        # 保存区域节点实时功率
        edge_node_powers[node_id] = actual_power

    except Exception as e:

        print("MQTT解析失败:", e)


mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


# ==========================================
# WebSocket
# ==========================================
@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    connected_websockets.append(websocket)

    print("🖥️ Dashboard 已连接")

    try:

        while True:
            await websocket.receive_text()

    except:

        if websocket in connected_websockets:
            connected_websockets.remove(websocket)

        print("❌ Dashboard 断开连接")


# ==========================================
# 广播函数
# ==========================================
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
# 云边协同主循环
# ==========================================
async def run_simulation_loop():

    orchestrator = GlobalOrchestrator()

    print("🚀 云边协同系统启动")

    await asyncio.sleep(5)

    while True:

        # ==================================
        # 新1小时调度周期
        # ==================================
        actual_curve.clear()

        # AI预测基线
        baseline_curve = np.random.normal(
            18000,
            1500,
            12
        )

        # 运筹优化目标
        target_curve = baseline_curve * np.random.uniform(
            0.82,
            0.92
        )

        baseline_curve = baseline_curve.tolist()
        target_curve = target_curve.tolist()

        print("\n☁️ 云端完成新一轮1小时优化")

        # ==================================
        # 向区域节点下发调度任务
        # ==================================
        for node_id in range(config.N_AREAS):

            # 每个区域平均目标
            regional_target = float(
                target_curve[0] /
                config.N_AREAS
            )

            payload = {

                "node_id": str(node_id),

                # 区域目标功率
                "power_set": regional_target,

                # 动态价格调节
                "price_adj_rate": float(
                    np.random.uniform(
                        -0.15,
                        0.15
                    )
                ),

                # 持续1小时
                "duration": 3600
            }

            mqtt_client.publish(
                config.TOPIC_CLOUD_SCHEDULE,
                json.dumps(payload)
            )

        print("📤 云端调度已下发")

        # ==================================
        # 推送云端规划到前端
        # ==================================
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

            # 等待边端执行
            await asyncio.sleep(2)

            # 聚合所有区域实时负荷
            total_actual_load = round(
                sum(edge_node_powers.values()),
                2
            )

            # 更新曲线
            actual_curve.append([
                step,
                total_actual_load
            ])

            print(
                f"📊 Step={step} "
                f"聚合实际负荷="
                f"{total_actual_load} kW"
            )

            # ==================================
            # 推送微观执行结果
            # ==================================
            await broadcast({

                "event_type":
                    "EDGE_MICRO_UPDATE_5MIN",

                "payload": {

                    "timestamp":
                        datetime.now().strftime(
                            "%H:%M:%S"
                        ),

                    "step": step,

                    # 当前总负荷
                    "actual_load":
                        total_actual_load,

                    # 完整轨迹
                    "actual_curve":
                        actual_curve,

                    # 节点数量
                    "active_nodes":
                        len(edge_node_powers)
                }
            })

        print("✅ 当前1小时滚动周期结束")


# ==========================================
# Startup
# ==========================================
@app.on_event("startup")
async def startup_event():

    # MQTT
    mqtt_client.connect(
        config.MQTT_BROKER,
        config.MQTT_PORT,
        config.MQTT_KEEPALIVE
    )

    mqtt_client.loop_start()

    print("✅ MQTT DataHub 已启动")

    # 启动云边主循环
    asyncio.create_task(
        run_simulation_loop()
    )


# ==========================================
# Main
# ==========================================
if __name__ == "__main__":

    uvicorn.run(
        "run_system:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )