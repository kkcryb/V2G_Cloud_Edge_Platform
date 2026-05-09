import subprocess
import time
import sys


def start_system():
    print("正在一键启动 V2G 云边控制平台...")

    processes = []
    try:
        # 1. 启动云端调度核心与前端 WebSocket 网关
        print("☁️ [1/2] 启动云端中心 (FastAPI + DataHub)...")
        cloud_proc = subprocess.Popen([sys.executable, "run_system.py"])
        processes.append(cloud_proc)

        # 给云端服务几秒钟启动时间，确保 MQTT 监听已就绪
        time.sleep(3)

        # 2. 启动边端仿真集群 (取代旧的 edge_simulation/main.py)
        print("[2/2] 启动边端并发仿真集群...")
        edge_proc = subprocess.Popen([sys.executable, "main.py"])  # 运行包含 EdgeFleetSimulator 的 main.py
        processes.append(edge_proc)

        print("全系统启动完毕！请访问前端 Dashboard。")

        # 守护进程
        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        print("正在关闭全系统...")
        for p in processes:
            p.terminate()


if __name__ == "__main__":
    start_system()