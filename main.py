import asyncio
import time
from datetime import datetime
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
import numpy as np

# 导入你写好的主厨逻辑
from system_runner import GlobalOrchestrator

app = FastAPI()

# 1. 挂载我们刚刚打包好的前端网页 (dist文件夹)
# 只要用户在浏览器输入网址，就把网页发给他
app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")


@app.get("/")
async def get_index():
    with open("dist/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# 2. 传菜员频道 (WebSocket)
connected_websockets = []


@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # 保持连接不断开
    except:
        connected_websockets.remove(websocket)


# 3. 改造主厨的工作流程，让他不仅 print，还能让传菜员送信
async def run_simulation_loop():
    orchestrator = GlobalOrchestrator()
    print("🚀 云边系统启动，等待前端连接...")
    await asyncio.sleep(5)  # 等待几秒钟，让你有时间打开浏览器

    # 这里对应你 system_runner.py 里的 SIMULATION_MODE 循环
    for hour in range(8, 24):
        # 让主厨干活
        orchestrator.run_hourly_dispatch()

        # 活干完后，让传菜员通知所有看着大屏的人 (前端)
        for ws in connected_websockets:
            await ws.send_json({
                "event_type": "CLOUD_DISPATCH_1H",
                "payload": {
                    "baseline": list(np.random.normal(50, 5, 12)),  # 这里填入你实际的预测曲线
                    "target": list(np.random.normal(40, 2, 12)),  # 这里填入你实际的目标曲线
                }
            })

        # 模拟边缘微观执行 (12个5分钟)
        for step in range(12):
            for ws in connected_websockets:
                await ws.send_json({
                    "event_type": "EDGE_MICRO_UPDATE_5MIN",
                    "payload": {
                        "timestamp": f"{hour:02d}:{step * 5:02d}",
                        "actual_load": float(np.random.normal(42, 1)),  # 这里填入微观执行结果
                        "step": step,
                        "v2g_progress": (step + 1) * (100 / 12)
                    }
                })
            await asyncio.sleep(1)  # 动画间隔1秒


@app.on_event("startup")
async def startup_event():
    # 启动网站的同时，在后台启动仿真死循环
    asyncio.create_task(run_simulation_loop())


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)