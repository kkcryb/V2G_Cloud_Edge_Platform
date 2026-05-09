import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import WriteOptions
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uvicorn

# 引入全局统一配置！取代原先几十行的硬编码
from shared_lib.config import config

# ==========================================
# 🔌 初始化数据库与客户端
# ==========================================
db_client = InfluxDBClient(
    url=config.INFLUX_URL,
    token=config.INFLUX_TOKEN,
    org=config.INFLUX_ORG,
    timeout=60000
)
write_api = db_client.write_api(write_options=WriteOptions(
    batch_size=500, flush_interval=1000, retry_interval=2000
))
query_api = db_client.query_api()

ws_manager = None
mqtt_client = None
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


# ==========================================
# 📡 WebSocket 管理类（面向前端大屏）
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🟢 [大屏 WS] 前端已连接，当前在线总数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"🔴 [大屏 WS] 前端断开，当前在线总数: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


ws_manager = ConnectionManager()


# ==========================================
# 📨 MQTT 消息处理（核心：记录流转数据）
# ==========================================
def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    print(f"✅ [DataHub MQTT] 已成功连接到 Broker ({config.MQTT_BROKER})")
    # 严格按照 config 订阅两大核心主题
    client.subscribe(config.TOPIC_EDGE_TO_CLOUD)  # 边端 -> 云端：上报5分钟级实时数据
    client.subscribe(config.TOPIC_CLOUD_SCHEDULE)  # 云端 -> 边端：1小时级宏观调度指令


def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))

        # ----------------------------------------------
        # 1. 记录运筹层(阶段一)下发的调度指令，供前端大屏展示对比
        # ----------------------------------------------
        if msg.topic == config.TOPIC_CLOUD_SCHEDULE:
            p = Point("cloud_schedule") \
                .tag("schedule_id", str(payload.get("schedule_id", "unknown"))) \
                .tag("node_id", str(payload.get("node_id", "unknown"))) \
                .field("price_adj_rate", float(payload.get("price_adj_rate", 0))) \
                .field("power_set_kw", float(payload.get("power_set", 0))) \
                .time(datetime.utcnow(), WritePrecision.NS)
            write_api.write(bucket=config.INFLUX_BUCKET_RAW, org=config.INFLUX_ORG, record=p)
            return

        # ----------------------------------------------
        # 2. 接收边端(阶段二)微观滚动追踪的实际上报数据，落盘入库
        # ----------------------------------------------
        if msg.topic == config.TOPIC_EDGE_TO_CLOUD:
            node_id = str(payload.get("node_id", "unknown"))
            power = float(payload.get("actual_power_kw", 0.0))
            soc = float(payload.get("current_soc", 0.0))

            p = Point("v2g_node_status") \
                .tag("node_id", node_id) \
                .field("power_kw", power) \
                .field("soc", soc) \
                .time(datetime.utcnow(), WritePrecision.NS)

            write_api.write(bucket=config.INFLUX_BUCKET_RAW, org=config.INFLUX_ORG, record=p)
            # 降低打印频率以免刷屏
            # print(f"📥 [边端回写] 节点 {node_id} 功率: {power}kW 写入成功")
            return

    except Exception as e:
        print(f"❌ [MQTT 数据解析/入库失败]: {e}")


# ==========================================
# ⏱️ 定时推送任务（聚合给前端大屏展示）
# ==========================================
async def scheduled_task_push_to_frontend():
    """定时聚合 InfluxDB 中的全网实时数据，推送到大屏"""
    if not ws_manager.active_connections:
        return
    try:
        # 查询全网过去1分钟内所有活跃节点的最新功率与SOC平均值
        flux_query = f'''
        from(bucket: "{config.INFLUX_BUCKET_RAW}")
          |> range(start: -1m)
          |> filter(fn: (r) => r._measurement == "v2g_node_status")
          |> filter(fn: (r) => r._field == "power_kw")
          |> last()
        '''
        tables = query_api.query(flux_query, org=config.INFLUX_ORG)

        total_power = 0.0
        active_nodes = 0
        for table in tables:
            for record in table.records:
                total_power += float(record.get_value())
                active_nodes += 1

        push_data = {
            "type": "realtime_update",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": {
                "total_grid_power_kw": round(total_power, 2),
                "active_nodes_count": active_nodes,
                "status": "online"
            }
        }
        await ws_manager.broadcast(push_data)

    except Exception as e:
        print(f"⚠️ [前端 WS 推送异常]: {e}")


# ==========================================
# 🚀 生命周期管理
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_client
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message

    try:
        mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"⚠️ [MQTT 启动连接异常]: {e}")

    # 启动大屏推送任务
    scheduler.add_job(scheduled_task_push_to_frontend, 'interval', seconds=config.WS_PUSH_INTERVAL)
    scheduler.start()

    yield

    # 安全退出
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    scheduler.shutdown()
    db_client.close()


# ==========================================
# 🌐 FastAPI Web 接口层
# ==========================================
app = FastAPI(title="V2G 云边协同数据中台 (Data Hub)", lifespan=lifespan, version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def format_influx_time(dt):
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


@app.get("/api/v1/history/power", summary="查询节点历史功率数据")
async def get_history_power(
        node_id: str = Query(..., description="节点ID（对应 N_AREAS 的索引或TAZID）"),
        start_range: str = Query("-24h", description="时间范围，如 -1h, -24h"),
):
    """
    提供给前端大屏展示单个充电站的历史功率曲线。
    修复了旧版查错表(volume)的问题，统一查 v2g_node_status。
    """
    try:
        flux_query = f'''
        from(bucket: "{config.INFLUX_BUCKET_RAW}")
          |> range(start: {start_range})
          |> filter(fn: (r) => r._measurement == "v2g_node_status")
          |> filter(fn: (r) => r.node_id == "{node_id}")
          |> filter(fn: (r) => r._field == "power_kw")
          |> aggregateWindow(every: 5m, fn: mean) 
          |> yield(name: "mean")
        '''
        tables = query_api.query(flux_query, org=config.INFLUX_ORG)
        result = []
        for table in tables:
            for record in table.records:
                if record.get_value() is not None:
                    result.append({
                        "time": format_influx_time(record.get_time()),
                        "power_kw": round(float(record.get_value()), 2)
                    })

        return {"code": 200, "msg": "ok", "count": len(result), "data": result}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": []}


@app.get("/api/v1/health", summary="健康检查接口")
async def health_check():
    return {
        "status": "online",
        "influxdb": "connected",
        "mqtt": "connected" if mqtt_client and mqtt_client.is_connected() else "disconnected"
    }


@app.websocket(config.WS_PATH)
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ==========================================
# 🏁 独立启动脚本
# ==========================================
if __name__ == "__main__":
    print("🚀 正在启动 Data Hub...")
    print(f"📍 WS 监听地址: ws://{config.WS_HOST}:{config.WS_PORT}{config.WS_PATH}")
    uvicorn.run("main:app", host=config.WS_HOST, port=config.WS_PORT, reload=False)