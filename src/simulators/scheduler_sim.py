"""
OS 调度算法模拟器
模拟 FCFS、Round Robin、CFS 三种调度算法，直观对比它们的行为差异。
"""
from dataclasses import dataclass
from collections import deque
import heapq


@dataclass
class Process:
    pid: int
    arrival_time: int
    burst_time: int
    priority: int = 0
    remaining_time: int = 0
    vruntime: float = 0
    waiting_time: int = 0
    completion_time: int = 0

    def __post_init__(self):
        self.remaining_time = self.burst_time


def fcfs(processes):
    """先来先服务：按到达顺序执行，非抢占"""
    procs = sorted([Process(**p.__dict__) for p in processes], key=lambda p: p.arrival_time)
    timeline = []
    current_time = 0
    for p in procs:
        if current_time < p.arrival_time:
            current_time = p.arrival_time
        p.waiting_time = current_time - p.arrival_time
        timeline.append((p.pid, current_time, current_time + p.burst_time))
        current_time += p.burst_time
        p.completion_time = current_time
    return timeline, procs


def round_robin(processes, quantum=2):
    """时间片轮转：每个进程运行 quantum 时间后切换"""
    procs = sorted([Process(**p.__dict__) for p in processes], key=lambda p: p.arrival_time)
    ready_queue = deque()
    timeline = []
    current_time = 0
    i = 0

    while ready_queue or i < len(procs):
        while i < len(procs) and procs[i].arrival_time <= current_time:
            ready_queue.append(procs[i])
            i += 1

        if not ready_queue:
            current_time = procs[i].arrival_time
            continue

        p = ready_queue.popleft()
        run_time = min(quantum, p.remaining_time)
        timeline.append((p.pid, current_time, current_time + run_time))
        current_time += run_time
        p.remaining_time -= run_time

        while i < len(procs) and procs[i].arrival_time <= current_time:
            ready_queue.append(procs[i])
            i += 1

        if p.remaining_time > 0:
            ready_queue.append(p)
        else:
            p.completion_time = current_time

    for p in procs:
        p.waiting_time = p.completion_time - p.arrival_time - p.burst_time

    return timeline, procs


def cfs(processes, target_latency=6):
    """CFS 模拟：基于 vruntime 的红黑树调度（用 heapq 模拟）"""
    procs = sorted([Process(**p.__dict__) for p in processes], key=lambda p: p.arrival_time)
    ready = []
    timeline = []
    current_time = 0
    i = 0

    while ready or i < len(procs):
        while i < len(procs) and procs[i].arrival_time <= current_time:
            heapq.heappush(ready, (procs[i].vruntime, procs[i].pid, procs[i]))
            i += 1

        if not ready:
            current_time = procs[i].arrival_time
            continue

        _, _, p = heapq.heappop(ready)
        nr_running = len(ready) + 1
        quantum = max(1, target_latency // nr_running)
        run_time = min(quantum, p.remaining_time)
        timeline.append((p.pid, current_time, current_time + run_time))
        current_time += run_time
        p.remaining_time -= run_time
        p.vruntime += run_time

        while i < len(procs) and procs[i].arrival_time <= current_time:
            heapq.heappush(ready, (procs[i].vruntime, procs[i].pid, procs[i]))
            i += 1

        if p.remaining_time > 0:
            heapq.heappush(ready, (p.vruntime, p.pid, p))
        else:
            p.completion_time = current_time

    for p in procs:
        p.waiting_time = p.completion_time - p.arrival_time - p.burst_time

    return timeline, procs


def print_results(name, timeline, procs):
    print(f"\n=== {name} ===")
    print("Timeline:")
    for pid, start, end in timeline:
        print(f"  P{pid}: [{start} → {end}]")
    avg_wait = sum(p.waiting_time for p in procs) / len(procs)
    avg_turn = sum(p.completion_time - p.arrival_time for p in procs) / len(procs)
    print(f"Average waiting time: {avg_wait:.1f}")
    print(f"Average turnaround time: {avg_turn:.1f}")


if __name__ == "__main__":
    procs = [
        Process(pid=1, arrival_time=0, burst_time=5),
        Process(pid=2, arrival_time=1, burst_time=3),
        Process(pid=3, arrival_time=2, burst_time=8),
        Process(pid=4, arrival_time=3, burst_time=6),
    ]

    tl, ps = fcfs(procs)
    print_results("FCFS", tl, ps)

    tl, ps = round_robin(procs, quantum=2)
    print_results("Round Robin (q=2)", tl, ps)

    tl, ps = cfs(procs, target_latency=6)
    print_results("CFS (latency=6)", tl, ps)