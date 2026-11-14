# 02 - 进程与调度

> "A process is the operating system's fundamental abstraction for a running program."

---

## 一、Design Philosophy：进程抽象在解决什么问题？

### 1.1 核心问题

单台计算机上只有一个 CPU（或少数几个核心），但我们需要"同时"运行几十甚至几百个程序。如何实现？

**进程抽象的核心思想：让每个程序以为自己独占整个计算机。**

这需要三个层面的支持：

1. **CPU 虚拟化**：通过时间片轮转，让每个进程轮流使用 CPU，每个进程都以为自己独占 CPU
2. **内存虚拟化**：通过虚拟内存，让每个进程拥有独立的地址空间（下一个主题详细讲）
3. **隔离**：一个进程的 bug 不能直接影响其他进程

### 1.2 进程 vs 程序

程序是**静态**的——磁盘上的一组指令和数据。
进程是**动态**的——程序的一次执行实例，包含运行时状态。

```
程序（磁盘上的 ELF 文件）
  → 加载到内存
    → 分配栈、堆
      → 创建进程控制块（PCB）
        → 进程（运行中的实例）
```

### 1.3 为什么需要"进程"而不是直接运行程序？

如果 OS 不提供进程抽象，裸机上运行多个程序需要：

```c
// 没有 OS 的多程序协作（协作式）
void program_a() {
    while (1) {
        do_work();
        yield();  // 主动让出 CPU
    }
}

void program_b() {
    while (1) {
        do_work();
        yield();
    }
}
```

问题：
- 每个程序必须**主动**让出 CPU——一个 bug（死循环）就能冻结整个系统
- 程序之间没有内存隔离——一个程序可以覆盖另一个程序的内存
- 没有统一的调度——谁先运行、运行多久完全靠自觉

**进程抽象通过硬件支持（时钟中断 + 特权级）强制实现 CPU 共享和内存隔离。**

---

## 二、Historical Evolution：进程模型的演进

### 2.1 早期批处理（1950s）

没有进程概念。一次只运行一个程序，运行完才加载下一个。

```
程序1 → 执行完毕 → 程序2 → 执行完毕 → 程序3 → ...
```

问题：CPU 大量时间在等待 I/O（读卡片、打印结果），利用率极低。

### 2.2 多道程序设计（1960s）

多个程序同时驻留内存，当一个程序等待 I/O 时，切换到另一个程序。

```
程序1（执行中） → 程序1（等待I/O） → 程序2（执行中） → 程序2（等待I/O） → 程序1（执行中）...
```

这是**进程**概念的雏形——OS 需要记录每个程序的执行状态（寄存器、PC、内存位置），才能在切换后恢复执行。

### 2.3 Unix 的进程模型（1970s）

Unix 确立了现代进程模型的核心设计：

1. **fork() + exec()** 分离创建和加载
2. **进程 = 地址空间 + 执行上下文**
3. **进程层次结构**（父-子关系）
4. **统一的进程标识**（PID）

### 2.4 线程的引入（1980s-1990s）

进程的问题：创建和切换开销大（需要切换地址空间）。

线程的解决方案：**同一进程内的多个执行流共享地址空间，但各有独立的栈和寄存器。**

```
进程 = 地址空间 + 资源（文件描述符、信号等）
线程 = 执行上下文（栈、寄存器、PC）

一个进程可以有多个线程
```

### 2.5 Linux 的线程实现：轻量级进程（LWP）

Linux 的独特设计：**线程和进程在内核中是同一个数据结构（task_struct）。**

- 创建进程：`clone()` with `CLONE_VM | CLONE_FILES | ...`（共享一切）
- 创建线程：`clone()` with 部分共享标志
- 创建进程（传统）：`fork()` = `clone()` without sharing

**设计哲学：统一抽象——用一套机制（task_struct + clone）实现进程和线程，通过参数控制共享程度。**

---

## 三、Core Mechanism：进程的内部实现

### 3.1 task_struct — 进程控制块（PCB）

`task_struct` 是 Linux 中最核心的数据结构之一，定义在 `include/linux/sched.h`：

```c
struct task_struct {
    // === 标识 ===
    pid_t pid;                          // 进程 ID
    pid_t tgid;                         // 线程组 ID（线程的 pid 不同，但 tgid 相同）
    struct task_struct *group_leader;   // 线程组 leader

    // === 状态 ===
    volatile long state;                // TASK_RUNNING, TASK_INTERRUPTIBLE, etc.

    // === 调度信息 ===
    int prio, static_prio, normal_prio; // 优先级
    unsigned int rt_priority;           // 实时优先级
    const struct sched_class *sched_class; // 调度类
    struct sched_entity se;             // CFS 调度实体
    struct sched_rt_entity rt;          // 实时调度实体

    // === 内存 ===
    struct mm_struct *mm;               // 进程地址空间（线程共享）
    struct mm_struct *active_mm;        // 当前活跃的地址空间

    // === 家族关系 ===
    struct task_struct *parent;         // 父进程
    struct list_head children;          // 子进程链表
    struct list_head sibling;           // 兄弟进程链表

    // === 文件 ===
    struct files_struct *files;         // 文件描述符表（线程共享）

    // === 信号 ===
    struct signal_struct *signal;       // 信号处理（线程共享）
    struct sighand_struct *sighand;     // 信号处理器表

    // === 内核栈 ===
    void *stack;                        // 内核栈

    // === 上下文 ===
    struct thread_struct thread;        // CPU 上下文（寄存器快照）
    
    // ... 还有几百个字段
};
```

**设计哲学：task_struct 是一个"上帝对象"——它包含了进程的所有信息。** 这违反了面向对象的"单一职责原则"，但在 OS 内核中，这是合理的：

- 内核需要频繁访问进程的所有信息，分散存储会增加缓存未命中
- 进程的所有属性在生命周期中紧密相关
- 内核代码不追求"优雅的抽象"，而是追求"高效的实现"

### 3.2 进程状态机

```
                    ┌──────────────┐
                    │  TASK_RUNNING │ ← 可运行（在运行队列中）
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │ 被调度执行  │            │ 时间片用完
              ▼            │            ▼
        ┌──────────┐       │      ┌──────────────┐
        │ 正在CPU上 │       │      │ 回到运行队列  │
        │ 执行     │       │      └──────────────┘
        └────┬─────┘       │
             │ 等待I/O     │
             ▼             │
    ┌──────────────────┐   │
    │TASK_INTERRUPTIBLE│   │ ← 可被信号唤醒
    │  (可中断睡眠)     │   │
    └────────┬─────────┘   │
             │ I/O完成     │
             ▼             │
    ┌──────────────────┐   │
    │ TASK_RUNNING     │   │ ← 回到运行队列
    └──────────────────┘   │
```

关键状态：

| 状态 | 含义 | 何时进入 | 何时退出 |
|------|------|---------|---------|
| `TASK_RUNNING` | 可运行（在运行队列中或正在执行） | 默认状态 | - |
| `TASK_INTERRUPTIBLE` | 可中断睡眠（等待事件，可被信号唤醒） | 等待 I/O、sleep() | 事件到来或收到信号 |
| `TASK_UNINTERRUPTIBLE` | 不可中断睡眠（等待事件，不可被信号唤醒） | 等待磁盘 I/O 等 | 事件到来 |
| `TASK_STOPPED` | 停止（收到 SIGSTOP 等） | 信号 SIGSTOP/SIGTSTP | 信号 SIGCONT |
| `EXIT_ZOMBIE` | 僵尸（已退出但父进程还没收尸） | exit() | 父进程 wait() |

**为什么有 `TASK_UNINTERRUPTIBLE`？** 因为某些操作（如等待磁盘 I/O 完成）不应该被信号打断——如果打断，数据可能处于不一致状态。这是**安全 vs 灵活**的权衡。

### 3.3 上下文切换（Context Switch）

上下文切换是进程管理的核心操作——保存当前进程的状态，加载下一个进程的状态。

```c
// 伪代码
void context_switch(struct task_struct *prev, struct task_struct *next) {
    // 1. 保存 prev 的寄存器到 prev->thread
    save_registers(&prev->thread);
    
    // 2. 切换地址空间（如果不同）
    if (prev->mm != next->mm)
        switch_mm(prev->active_mm, next->active_mm, next);
    
    // 3. 切换内核栈
    switch_to(prev, next, prev);
    
    // 4. 加载 next 的寄存器从 next->thread
    // （此时已经在 next 的栈上执行了）
    restore_registers(&next->thread);
}
```

实际实现（x86-64，简化）：

```asm
; arch/x86/kernel/process_64.c: __switch_to_asm
__switch_to_asm:
    ; 保存 callee-saved 寄存器到当前栈
    pushq   %rbp
    pushq   %rbx
    pushq   %r12
    pushq   %r13
    pushq   %r14
    pushq   %r15
    
    ; 保存当前栈指针到 prev->thread.sp
    movq    %rsp, TASK_threadsp(%rdi)
    
    ; 加载 next->thread.sp 到栈指针
    movq    TASK_threadsp(%rsi), %rsp
    
    ; 恢复 callee-saved 寄存器从新栈
    popq    %r15
    popq    %r14
    popq    %r13
    popq    %r12
    popq    %rbx
    popq    %rbp
    
    ; 跳转到 __switch_to 完成 TLB 刷新等
    jmp     __switch_to
```

**上下文切换的开销**：

1. **直接开销**：保存/恢复寄存器（~100-200 cycles）
2. **间接开销**：TLB 刷新（切换地址空间时）、缓存失效（~1000-10000 cycles）

**为什么切换地址空间这么贵？** 因为切换 CR3（页表基址寄存器）会导致 TLB 全部失效，后续的内存访问都需要重新走页表翻译，大量 cache miss。

**优化：内核线程共享内核地址空间**。当从用户进程切换到内核线程时，不需要切换地址空间（`prev->active_mm == next->active_mm`），避免了 TLB 刷新。

### 3.4 fork() 的实现：写时复制（COW）

fork() 创建子进程时，不是立即复制父进程的所有内存页，而是让子进程共享父进程的页，标记为只读。当任一进程写入时，才触发缺页异常，复制该页。

```c
// kernel/fork.c（简化）
long _do_fork(unsigned long clone_flags, ...)
{
    struct task_struct *p;
    
    // 1. 分配新的 task_struct
    p = copy_process(clone_flags, ...);
    
    // 2. 唤醒新进程
    wake_up_new_task(p);
    
    return p->pid;
}

static struct task_struct *copy_process(unsigned long clone_flags, ...)
{
    struct task_struct *p;
    
    // 分配 task_struct
    p = dup_task_struct(current);
    
    // 复制内存空间（COW）
    if (clone_flags & CLONE_VM)
        p->mm = current->mm;        // 线程：共享地址空间
    else
        p->mm = copy_mm(clone_flags, current->mm);  // 进程：COW 复制
    
    // 复制文件描述符表
    if (clone_flags & CLONE_FILES)
        p->files = current->files;  // 线程：共享
    else
        p->files = copy_files(clone_flags, current->files);  // 进程：复制
    
    // 复制信号处理器
    // ...
    
    return p;
}
```

**COW 的设计哲学：延迟昂贵操作——只在真正需要时才付出代价。**

如果子进程立即 exec()（这是最常见的模式），那么复制的页全部被丢弃，COW 避免了这次无用复制。

---

## 四、调度器：从 O(n) 到 CFS 到 EEVDF

### 4.1 调度器的核心问题

给定 N 个可运行进程和 M 个 CPU 核心，如何决定：
- 哪个进程在哪个核心上运行？
- 每个进程运行多长时间？
- 何时切换？

**调度目标**（互相矛盾）：
- **公平性**：每个进程获得公平的 CPU 份额
- **吞吐量**：单位时间内完成尽可能多的工作
- **延迟**：交互式应用的响应时间尽可能短
- **优先级**：重要进程优先获得 CPU

### 4.2 O(n) 调度器（Linux 2.4）

```c
// 简化的 O(n) 调度器逻辑
struct task_struct *pick_next_task() {
    struct task_struct *best = NULL;
    int best_goodness = 0;
    
    // 遍历所有可运行进程，找 goodness 最大的
    for_each_task(p) {
        if (p->state != TASK_RUNNING) continue;
        int goodness = calculate_goodness(p);
        if (goodness > best_goodness) {
            best_goodness = goodness;
            best = p;
        }
    }
    return best;
}
```

**问题**：每次调度都要遍历所有进程，复杂度 O(n)。当进程数达到数千时，调度开销显著。

### 4.3 O(1) 调度器（Linux 2.6, 2002）

Ingo Molnár 的设计：用**优先级数组**替代遍历。

```c
struct prio_array {
    DECLARE_BITMAP(bitmap, MAX_PRIO);  // 140个优先级的位图
    struct list_head queue[MAX_PRIO];  // 每个优先级一个链表
};

struct runqueue {
    struct prio_array *active;   // 活跃队列
    struct prio_array *expired;  // 过期队列
};
```

调度逻辑：
1. 在位图中找第一个被设置的位（O(1)）
2. 从该优先级的链表中取第一个进程（O(1)）

**问题**：
- 优先级映射复杂（nice 值到时间片的映射不直观）
- 交互式进程的判定启发式算法复杂且容易出错
- 不够公平——不同 nice 值的进程获得的 CPU 时间差异非线性

### 4.4 CFS — 完全公平调度器（Linux 2.6.23, 2007）

CFS（Completely Fair Scheduler）的核心思想：**维护每个进程的"虚拟运行时间"（vruntime），总是调度 vruntime 最小的进程。**

```c
struct sched_entity {
    struct rb_node run_node;     // 红黑树节点
    u64 vruntime;                // 虚拟运行时间
    u64 exec_start;              // 本次开始执行的时间
    u64 sum_exec_runtime;        // 总执行时间
    // ...
};
```

vruntime 的计算：

```c
// 简化的 vruntime 更新逻辑
void update_vruntime(struct sched_entity *se, u64 delta_exec) {
    // delta_exec: 实际运行时间
    // 根据优先级缩放：优先级越高，vruntime 增长越慢
    u64 delta_vruntime = delta_exec * weight_of_0 / se->load.weight;
    se->vruntime += delta_vruntime;
}
```

**关键设计**：
- 优先级高的进程（nice 值低）的 `load.weight` 大，vruntime 增长慢 → 更频繁被调度
- 优先级低的进程的 `load.weight` 小，vruntime 增长快 → 较少被调度
- 但**每个进程都会被调度**——不会饿死

数据结构：**红黑树**，按 vruntime 排序。最左边的节点（vruntime 最小）就是下一个要运行的进程。

```
红黑树（按 vruntime 排序）：

         [vruntime=50]
        /              \
   [vruntime=20]    [vruntime=80]
   /        \
[vruntime=10] [vruntime=30]

→ 最左节点 vruntime=10 是下一个运行的进程
```

**CFS 的设计哲学：用数学公式定义"公平"，用数据结构高效实现。**

### 4.5 EEVDF — 最早虚拟截止时间优先（Linux 6.6, 2023）

CFS 的问题：对延迟敏感的工作负载（如交互式应用）响应不够好。

EEVDF（Earliest Eligible Virtual Deadline First）的改进：
- 引入**虚拟截止时间**（virtual deadline）概念
- 优先调度截止时间最早的进程
- 更精确的延迟控制

```c
// EEVDF 的核心逻辑（简化）
// 每个调度实体有一个 lag（滞后量）和 deadline
struct sched_entity {
    s64 lag;           // 滞后量：实际获得的 CPU 时间 vs 应获得的
    u64 deadline;      // 虚拟截止时间
    u64 vruntime;
};

// 调度决策：
// 1. 找 lag <= 0 的进程（"有资格"运行的进程）
// 2. 在有资格的进程中，选 deadline 最早的
```

---

## 五、Trade-offs：调度器设计中的关键权衡

### 5.1 时间片大小

| 时间片 | 优点 | 缺点 |
|--------|------|------|
| 大（100ms） | 上下文切换开销小、吞吐量高 | 交互式响应慢 |
| 小（1ms） | 交互式响应快 | 上下文切换开销占比大 |
| 动态 | 兼顾两者 | 实现复杂 |

**CFS 的选择**：动态——目标延迟（target latency）内每个进程至少运行一次。默认 target latency = 6ms，时间片 = target_latency / nr_running。

### 5.2 全局队列 vs per-CPU 队列

| 方案 | 优点 | 缺点 |
|------|------|------|
| 全局队列 | 简单、自动负载均衡 | 锁竞争严重（多核时） |
| per-CPU 队列 | 无锁竞争、缓存友好 | 需要负载均衡机制 |

**Linux 的选择**：per-CPU 运行队列 + 定期负载均衡。每个 CPU 有自己的 `struct rq`，定期检查其他 CPU 的队列是否更空闲，必要时迁移进程。

### 5.3 抢占式 vs 协作式

| 方案 | 优点 | 缺点 |
|------|------|------|
| 协作式 | 简单、上下文切换只在安全点 | 一个进程可以霸占 CPU |
| 抢占式 | 公平、响应性好 | 需要在任意点保存状态、复杂 |

**Linux 的选择**：抢占式 + 多个抢占点：
- 用户态抢占：时钟中断返回用户态时检查是否需要调度
- 内核态抢占（CONFIG_PREEMPT）：内核代码也可以被抢占（实时性要求高的场景）
- 自愿抢占（CONFIG_PREEMPT_VOLUNTARY）：内核代码在显式的 `might_sleep()` 点检查

---

## 六、Real-world Analysis：Linux 调度器源码

### 6.1 调度类（sched_class）

Linux 调度器通过**调度类**实现策略的可插拔：

```c
// include/linux/sched.h
struct sched_class {
    const struct sched_class *next;     // 链表：下一个调度类
    
    void (*enqueue_task)(struct rq *rq, struct task_struct *p, int flags);
    void (*dequeue_task)(struct rq *rq, struct task_struct *p, int flags);
    
    struct task_struct *(*pick_next_task)(struct rq *rq);
    
    void (*put_prev_task)(struct rq *rq, struct task_struct *p);
    void (*set_next_task)(struct rq *rq, struct task_struct *p, bool first);
    
    void (*task_tick)(struct rq *rq, struct task_struct *p, int queued);
    // ...
};
```

调度类的优先级顺序：

```
stop_sched_class → dl_sched_class → rt_sched_class → fair_sched_class → idle_sched_class
   (最高优先级)      (deadline)       (实时)           (CFS/EEVDF)       (idle)
```

`pick_next_task()` 按优先级顺序依次调用每个调度类的 `pick_next_task`，第一个返回非 NULL 的就是下一个运行的进程。

**设计哲学：调度类是策略模式的内核实现——不同的调度策略通过统一的接口插入调度框架。**

### 6.2 CFS 的核心数据结构

```c
// kernel/sched/fair.c
struct cfs_rq {
    struct rb_root_cached tasks_timeline;  // 红黑树（按 vruntime 排序）
    struct sched_entity *curr;             // 当前运行的调度实体
    u64 min_vruntime;                      // 最小 vruntime（用于新进程初始化）
    u64 avg_vruntime;                      // 平均 vruntime（EEVDF 使用）
    s64 avg_load;                          // 平均负载
    // ...
};
```

`pick_next_task` 的核心逻辑（简化）：

```c
struct task_struct *pick_next_task_fair(struct rq *rq)
{
    struct cfs_rq *cfs_rq = &rq->cfs;
    struct sched_entity *se;
    
    // 1. 从红黑树中找最左节点（vruntime 最小）
    se = __pick_first_entity(cfs_rq);
    if (!se)
        return NULL;
    
    // 2. 获取对应的 task_struct
    return task_of(se);
}
```

### 6.3 负载均衡

```c
// kernel/sched/fair.c（简化）
void rebalance_domains(struct rq *rq, enum cpu_idle_type idle)
{
    // 定期检查：当前 CPU 是否过载？其他 CPU 是否更空闲？
    // 如果是，迁移一些进程到更空闲的 CPU
    
    for_each_domain(cpu, sd) {
        // sd: 调度域（SMT → MC → NUMA → ...）
        if (sd->flags & SD_BALANCE_LOAD) {
            load_balance(cpu, rq, sd, idle, &balance);
        }
    }
}
```

**调度域（sched_domain）**是负载均衡的关键概念——它描述了 CPU 的拓扑结构：

```
SMT 域（超线程兄弟）
  → MC 域（同一物理核）
    → NUMA 域（同一 NUMA 节点）
      → 全局域
```

负载均衡优先在低层级域内进行（因为迁移代价更小——缓存更近）。

---

## 七、Hands-on Lab：lab02-scheduler

### 实验目标

1. 用 Python 模拟 5 种调度算法，直观理解它们的差异
2. 用 C 实现一个简单的上下文切换

### 实验1：Python 调度算法模拟器

```python
# src/simulators/scheduler_sim.py
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
    vruntime: float = 0  # for CFS
    
    def __post_init__(self):
        self.remaining_time = self.burst_time

def fcfs(processes):
    """先来先服务"""
    processes = sorted(processes, key=lambda p: p.arrival_time)
    timeline = []
    current_time = 0
    for p in processes:
        if current_time < p.arrival_time:
            current_time = p.arrival_time
        timeline.append((p.pid, current_time, current_time + p.burst_time))
        current_time += p.burst_time
    return timeline

def round_robin(processes, quantum=2):
    """时间片轮转"""
    processes = sorted(processes, key=lambda p: p.arrival_time)
    ready_queue = deque()
    timeline = []
    current_time = 0
    i = 0
    
    while ready_queue or i < len(processes):
        while i < len(processes) and processes[i].arrival_time <= current_time:
            ready_queue.append(processes[i])
            i += 1
        
        if not ready_queue:
            current_time = processes[i].arrival_time
            continue
        
        p = ready_queue.popleft()
        run_time = min(quantum, p.remaining_time)
        timeline.append((p.pid, current_time, current_time + run_time))
        current_time += run_time
        p.remaining_time -= run_time
        
        while i < len(processes) and processes[i].arrival_time <= current_time:
            ready_queue.append(processes[i])
            i += 1
        
        if p.remaining_time > 0:
            ready_queue.append(p)
    
    return timeline

def cfs(processes, target_latency=6):
    """CFS 模拟（简化版）"""
    processes = sorted(processes, key=lambda p: p.arrival_time)
    ready = []
    timeline = []
    current_time = 0
    i = 0
    
    while ready or i < len(processes):
        while i < len(processes) and processes[i].arrival_time <= current_time:
            heapq.heappush(ready, (processes[i].vruntime, processes[i]))
            i += 1
        
        if not ready:
            current_time = processes[i].arrival_time
            continue
        
        _, p = heapq.heappop(ready)
        nr_running = len(ready) + 1
        quantum = max(1, target_latency // nr_running)
        run_time = min(quantum, p.remaining_time)
        timeline.append((p.pid, current_time, current_time + run_time))
        current_time += run_time
        p.remaining_time -= run_time
        p.vruntime += run_time  # 简化：不考虑优先级缩放
        
        while i < len(processes) and processes[i].arrival_time <= current_time:
            heapq.heappush(ready, (processes[i].vruntime, processes[i]))
            i += 1
        
        if p.remaining_time > 0:
            heapq.heappush(ready, (p.vruntime, p))
    
    return timeline

# 测试
if __name__ == "__main__":
    procs = [
        Process(pid=1, arrival_time=0, burst_time=5),
        Process(pid=2, arrival_time=1, burst_time=3),
        Process(pid=3, arrival_time=2, burst_time=8),
        Process(pid=4, arrival_time=3, burst_time=6),
    ]
    
    print("FCFS:", fcfs([Process(**p.__dict__) for p in procs]))
    print("RR:  ", round_robin([Process(**p.__dict__) for p in procs]))
    print("CFS: ", cfs([Process(**p.__dict__) for p in procs]))
```

### 实验2：C 上下文切换

```c
// src/mini-kernel/context_switch.c
#include <stdio.h>
#include <ucontext.h>
#include <stdlib.h>

#define STACK_SIZE 16384

ucontext_t main_ctx, ctx_a, ctx_b;

void func_a() {
    for (int i = 0; i < 3; i++) {
        printf("Process A: step %d\n", i);
        swapcontext(&ctx_a, &ctx_b);  // 切换到 B
    }
    printf("Process A: done\n");
    swapcontext(&ctx_a, &main_ctx);   // 切回 main
}

void func_b() {
    for (int i = 0; i < 3; i++) {
        printf("Process B: step %d\n", i);
        swapcontext(&ctx_b, &ctx_a);  // 切换到 A
    }
    printf("Process B: done\n");
    swapcontext(&ctx_b, &main_ctx);   // 切回 main
}

int main() {
    char stack_a[STACK_SIZE];
    char stack_b[STACK_SIZE];

    // 初始化上下文 A
    getcontext(&ctx_a);
    ctx_a.uc_stack.ss_sp = stack_a;
    ctx_a.uc_stack.ss_size = STACK_SIZE;
    ctx_a.uc_link = &main_ctx;
    makecontext(&ctx_a, func_a, 0);

    // 初始化上下文 B
    getcontext(&ctx_b);
    ctx_b.uc_stack.ss_sp = stack_b;
    ctx_b.uc_stack.ss_size = STACK_SIZE;
    ctx_b.uc_link = &main_ctx;
    makecontext(&ctx_b, func_b, 0);

    printf("=== Start scheduling ===\n");
    swapcontext(&main_ctx, &ctx_a);  // 启动 A
    printf("=== All processes done ===\n");

    return 0;
}
```

编译运行：
```bash
gcc context_switch.c -o context_switch && ./context_switch
```

### 进阶实验

- 在 Python 模拟器中添加优先级缩放（nice 值 → weight → vruntime 增长率）
- 实现多核负载均衡模拟
- 添加 I/O 等待模拟（进程在 I/O 时进入 TASK_INTERRUPTIBLE，完成后回到运行队列）

---

## 参考资源

- Linux 源码 `kernel/sched/` — 调度器实现
- Linux 源码 `include/linux/sched.h` — task_struct 定义
- *Understanding the Linux Kernel* Ch.3 — 进程调度
- *Linux Kernel Development* Ch.4 — 进程管理
- CFS 论文：https://www.kernel.org/doc/Documentation/scheduler/sched-design-CFS.rst
- EEVDF 论文：https://en.wikipedia.org/wiki/Earliest_eligible_virtual_deadline_first