MAX_DISCHARGE_POWER = 60.0  # 充电桩最大放电功率，单位kW
STEP_INTERVAL = 300         # 控制步长，5分钟=300秒
SIMULATION_MODE = True      # 仿真模式开关：True=用模拟数据，False=对接真实接口
MQTT_BROKER = "127.0.0.1"   # MQTT服务器地址，后期队友给了再改
MQTT_PORT = 1883            # MQTT端口
SUB_TOPIC = "v2g/edge/command"  # 订阅指令主题
PUB_TOPIC = "v2g/edge/report"   # 上报数据主题