import logging
import time
import random
import csv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("edge_runtime.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# 配置参数
STEP_INTERVAL = 300
SIMULATION_MODE = True

# 边端控制核心
class EdgeController:
    def __init__(self):
        self.target_kwh = 0.0
        self.finished_kwh = 0.0
        self.remain_step = 12
        self.current_price = 0.0

    def set_task(self, target_kwh, price):
        self.target_kwh = target_kwh
        self.current_price = price
        self.finished_kwh = 0.0
        self.remain_step = 12

    def run_step(self, current_load):
        if self.remain_step <= 0:
            return 0.0, 0.0

        p_theory = (self.target_kwh - self.finished_kwh) / self.remain_step
        p_actual = min(p_theory, 60.0, current_load)
        kwh = p_actual * 5 / 60

        self.finished_kwh += kwh
        self.remain_step -= 1
        return round(p_actual, 2), round(kwh, 2)

# 仿真负荷
def simulate_load():
    hour = time.localtime().tm_hour
    base_load = 40 + hour * 2
    noise = random.uniform(-10, 15)
    return round(max(base_load + noise, 20), 2)

# 保存结果到 CSV
def save_to_csv(results):
    with open("edge_result.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["时间", "负荷(kW)", "功率(kW)", "电量(kWh)", "累计(kWh)"])
        writer.writerows(results)

# 主程序
def main():
    print("🚀 边端V2G控制程序启动")
    logging.info("程序启动")

    controller = EdgeController()
    controller.set_task(target_kwh=50.0, price=0.8)
    print("🔧 仿真模式：1小时放电50kWh")

    results = []

    # 跑完一轮就结束，不无限循环
    while controller.remain_step > 0:
        print("\n" + "="*40)
        now_time = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"⏰ 当前时间：{now_time}")

        current_load = simulate_load()
        print(f"📊 仿真充电负荷：{current_load} kW")

        power, kwh = controller.run_step(current_load)
        print(f"⚡ 放电功率：{power} kW，放电量：{kwh} kWh")
        print(f"📈 累计：{controller.finished_kwh} kWh，剩余步数：{controller.remain_step}")

        # 记录日志
        logging.info(f"负荷:{current_load} 功率:{power} 电量:{kwh} 累计:{controller.finished_kwh}")

        # 保存数据
        results.append([now_time, current_load, power, kwh, controller.finished_kwh])

        print("⌛ 5秒后继续...")
        time.sleep(5)

    # 运行结束保存文件
    save_to_csv(results)
    print("\n✅ 任务完成！数据已保存 → edge_result.csv + edge_runtime.log")
    logging.info("任务完成")

if __name__ == "__main__":
    main()

