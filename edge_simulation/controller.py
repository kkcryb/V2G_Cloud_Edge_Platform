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