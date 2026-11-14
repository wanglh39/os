"""
I/O 调度算法模拟器
对比 FIFO、SSTF、SCAN、CSCAN 四种磁盘调度算法的寻道距离。
"""


class IOSchedulerSimulator:
    def __init__(self, disk_size=1000):
        self.disk_size = disk_size
        self.current_position = 0
        self.requests = []

    def add_request(self, sector):
        self.requests.append(sector)

    def fifo(self):
        seq = list(self.requests)
        total_seek = 0
        pos = self.current_position
        for req in seq:
            total_seek += abs(req - pos)
            pos = req
        return seq, total_seek

    def sstf(self):
        remaining = list(self.requests)
        seq = []
        total_seek = 0
        pos = self.current_position
        while remaining:
            closest = min(remaining, key=lambda r: abs(r - pos))
            total_seek += abs(closest - pos)
            pos = closest
            seq.append(closest)
            remaining.remove(closest)
        return seq, total_seek

    def scan(self, direction=1):
        remaining = sorted(self.requests)
        seq = []
        total_seek = 0
        pos = self.current_position

        if direction == 1:
            up = [r for r in remaining if r >= pos]
            down = [r for r in remaining if r < pos]
            for r in up:
                total_seek += abs(r - pos)
                pos = r
                seq.append(r)
            for r in reversed(down):
                total_seek += abs(r - pos)
                pos = r
                seq.append(r)
        else:
            down = [r for r in remaining if r <= pos]
            up = [r for r in remaining if r > pos]
            for r in reversed(down):
                total_seek += abs(r - pos)
                pos = r
                seq.append(r)
            for r in up:
                total_seek += abs(r - pos)
                pos = r
                seq.append(r)
        return seq, total_seek

    def cscan(self, direction=1):
        remaining = sorted(self.requests)
        seq = []
        total_seek = 0
        pos = self.current_position

        up = [r for r in remaining if r >= pos]
        down = [r for r in remaining if r < pos]

        for r in up:
            total_seek += abs(r - pos)
            pos = r
            seq.append(r)
        if down:
            total_seek += pos
            pos = 0
            for r in down:
                total_seek += abs(r - pos)
                pos = r
                seq.append(r)
        return seq, total_seek


if __name__ == "__main__":
    sim = IOSchedulerSimulator()
    sim.current_position = 50
    requests = [98, 183, 37, 122, 14, 124, 65, 67]
    for r in requests:
        sim.add_request(r)

    print(f"Current position: {sim.current_position}")
    print(f"Requests: {requests}\n")

    for name, func in [("FIFO", sim.fifo),
                        ("SSTF", sim.sstf),
                        ("SCAN", lambda: sim.scan(1)),
                        ("CSCAN", lambda: sim.cscan(1))]:
        seq, seek = func()
        print(f"{name:6s}: sequence={seq}, total_seek={seek}")