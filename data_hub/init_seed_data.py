# data_hub/init_seed_data.py
import pandas as pd
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from shared_lib.config import config
import os


def seed_database():
    print("⏳ 开始进行冷启动仿真初始化，导入 UrbanEV 历史数据集...")

    # 连接 InfluxDB
    client = InfluxDBClient(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    # 假设你存放数据的路径
    csv_path = "../ai_prediction/training/data/volume.csv"
    if not os.path.exists(csv_path):
        print(f"❌ 找不到原始数据文件: {csv_path}")
        return

    # 读取真实数据集
    df = pd.read_csv(csv_path)

    # 模拟“过去24小时”的时间戳
    now = datetime.utcnow()
    points = []

    print("📊 正在拼装时序数据点...")
    for idx, row in df.head(5000).iterrows():  # 示例: 导入前5000条作为历史冷启动数据
        # 这里假设 df 有 node_id, power_kw 等字段
        # 实际你需要根据你的 volume.csv 列名来调整
        node_id = str(row.get('station_id', row.get('node_id', 'unknown')))
        power = float(row.get('volume', row.get('power_kw', 0.0)))

        # 将数据的时间戳伪装成过去 24 小时内，以便 AI 能够立马拉取到
        fake_time = now - timedelta(minutes=(5000 - idx) * 5)

        p = Point("v2g_node_status") \
            .tag("node_id", node_id) \
            .field("power_kw", power) \
            .field("soc", 0.5) \
            .time(fake_time, WritePrecision.NS)
        points.append(p)

        # 分批写入防内存溢出
        if len(points) >= 500:
            write_api.write(bucket=config.INFLUX_BUCKET_RAW, record=points)
            points = []
            print(f"   已写入 {idx} 条...")

    # 写入残留
    if points:
        write_api.write(bucket=config.INFLUX_BUCKET_RAW, record=points)

    print("✅ 数据冷启动初始化完成！AI预测层现在可以读取历史数据了。")
    client.close()


if __name__ == "__main__":
    seed_database()
