# 06 - I/O 与设备驱动

> "The purpose of abstraction is not to be vague, but to create a new semantic level in which one can be absolutely precise." — Edsger Dijkstra

---

## 一、Design Philosophy：I/O 子系统在解决什么问题？

### 1.1 核心问题

计算机有各种各样的 I/O 设备：磁盘、网卡、键盘、鼠标、显示器、USB 设备……每种设备的接口、协议、性能特征都不同。

**I/O 子系统的核心使命：在多样化的硬件之上提供统一的抽象，让应用程序不需要关心设备细节。**

具体解决三个问题：

1. **统一接口**：不同设备用同一套 API 操作
2. **性能优化**：利用 DMA、中断、缓冲等技术减少 CPU 开销
3. **设备管理**：设备的发现、初始化、热插拔

### 1.2 I/O 的三种基本方式

```
方式1：轮询（Polling）
  CPU 反复检查设备状态寄存器
  → 简单但 CPU 利用率极低

方式2：中断（Interrupt）
  CPU 发出 I/O 请求后去做别的事
  设备完成后发中断通知 CPU
  → CPU 利用率高但中断处理有开销

方式3：DMA（Direct Memory Access）
  CPU 配置 DMA 控制器：源地址、目标地址、传输长度
  DMA 控制器直接在设备和内存之间传输数据
  完成后发中断通知 CPU
  → CPU 几乎不参与数据传输
```

**设计哲学：让 CPU 尽可能少地参与 I/O——CPU 的时间应该用来计算，而不是搬运数据。**

---

## 二、Historical Evolution：I/O 的演进

### 2.1 程序化 I/O（PIO）

最早的 I/O 方式——CPU 直接读写设备寄存器：

```c
// 从磁盘读取一个扇区（PIO 方式）
void disk_read_pio(int sector, char *buffer) {
    // 1. 设置磁盘控制器寄存器
    outb(0x1F2, 1);           // 扇区数
    outb(0x1F3, sector);      // 扇区号低8位
    outb(0x1F4, sector >> 8); // 扇区号中8位
    outb(0x1F5, sector >> 16);// 扇区号高8位
    outb(0x1F6, 0xE0);        // 选择驱动器
    outb(0x1F7, 0x20);        // 读命令

    // 2. 轮询等待
    while (!(inb(0x1F7) & 0x08))  // 等待 DRQ 位
        ;

    // 3. 逐字读取数据
    for (int i = 0; i < 256; i++) {
        ((short*)buffer)[i] = inw(0x1F0);
    }
}
```

问题：CPU 在等待和搬运数据上浪费大量时间。

### 2.2 中断驱动 I/O

```c
// 中断方式
void disk_read_interrupt(int sector, char *buffer) {
    // 1. 设置磁盘控制器（同上）
    outb(0x1F7, 0x20);

    // 2. CPU 去做别的事（不需要轮询！）
    // 当前进程进入睡眠，调度器切换到其他进程

    // 3. 磁盘完成后发中断
    // → 中断处理程序唤醒等待的进程
}

// 中断处理程序
void disk_irq_handler() {
    // 读取数据
    for (int i = 0; i < 256; i++) {
        ((short*)buffer)[i] = inw(0x1F0);
    }
    // 唤醒等待的进程
    wake_up(&disk_wait_queue);
}
```

改善：CPU 不再轮询等待。但数据搬运仍然由 CPU 完成。

### 2.3 DMA

```c
// DMA 方式
void disk_read_dma(int sector, char *buffer) {
    // 1. 配置 DMA 控制器
    dma_set_source(DMA_DISK, sector);
    dma_set_dest(DMA_DISK, buffer);      // 目标：内存地址
    dma_set_count(DMA_DISK, 512);        // 传输长度
    dma_set_direction(DMA_DISK, DEV_TO_MEM);

    // 2. 启动 DMA
    dma_enable(DMA_DISK);

    // 3. CPU 去做别的事
    // DMA 控制器自动把数据从磁盘搬到内存

    // 4. DMA 完成后发中断
    // → 中断处理程序只需唤醒进程，不需要搬运数据
}
```

**DMA 的革命性**：CPU 只需要"发起"和"收尾"，中间的数据传输完全由硬件完成。

### 2.4 现代演进

| 技术 | 描述 | 优势 |
|------|------|------|
| DMA | 硬件直接搬运数据 | CPU 不参与数据搬运 |
| Scatter-Gather DMA | 一次 DMA 传输到多个不连续的内存区域 | 减少中断次数 |
| NVMe | PCIe 总线直接访问 SSD，绕过 SATA 控制器 | 极低延迟、高并行 |
| io_uring | Linux 新的异步 I/O 接口 | 减少 syscall 开销 |

---

## 三、Core Mechanism：Linux I/O 子系统

### 3.1 I/O 子系统的分层架构

```
┌─────────────────────────────────────────┐
│  应用程序                                │
│  read() / write() / poll() / epoll()    │
├─────────────────────────────────────────┤
│  系统调用层                              │
│  sys_read / sys_write / sys_epoll_wait  │
├─────────────────────────────────────────┤
│  VFS 层                                  │
│  统一的文件操作接口                      │
├─────────────────────────────────────────┤
│  页缓存 / Direct I/O                     │
│  缓存管理                                │
├─────────────────────────────────────────┤
│  块设备层 (Block Layer)                  │
│  I/O 调度、请求队列、合并                │
├─────────────────────────────────────────┤
│  设备驱动                                │
│  具体设备的操作实现                      │
├─────────────────────────────────────────┤
│  硬件                                    │
│  磁盘 / SSD / 网卡 / USB                 │
└─────────────────────────────────────────┘
```

### 3.2 字符设备 vs 块设备 vs 网络设备

Linux 把设备分为三大类：

| 类型 | 特点 | 示例 | 访问方式 |
|------|------|------|---------|
| 字符设备 | 顺序访问、不可 seek | 键盘、鼠标、串口 | read/write 逐字节 |
| 块设备 | 随机访问、可 seek | 磁盘、SSD、USB存储 | read/write 逐块 |
| 网络设备 | 包传输、无文件接口 | 网卡 | socket API |

**为什么区分字符设备和块设备？** 因为块设备需要缓冲、I/O 调度、请求合并等复杂机制，而字符设备只需要简单的数据流传输。

### 3.3 块设备层（Block Layer）

块设备层是 I/O 子系统中最复杂的部分：

```c
// include/linux/blkdev.h（简化）
struct request_queue {
    struct list_head queue_head;     // 请求链表
    struct request *last_merge;      // 最后合并的请求
    struct elevator_queue *elevator; // I/O 调度器
    unsigned long nr_requests;       // 最大请求数
    // ...
};

struct request {
    struct list_head queuelist;      // 链表节点
    struct request_queue *q;         // 所属队列
    sector_t sector;                 // 起始扇区
    unsigned int nr_phys_segments;   // 物理段数
    struct bio *bio;                 // bio 链表
    // ...
};

struct bio {
    struct block_device *bi_bdev;    // 目标块设备
    sector_t bi_sector;              // 起始扇区
    unsigned int bi_size;            // 数据大小
    struct bio_vec *bi_io_vec;       // 段数组
    unsigned short bi_vcnt;          // 段数
    bio_end_io_t *bi_end_io;         // 完成回调
    void *bi_private;                // 私有数据
    // ...
};
```

**数据流**：

```
read() → VFS → 页缓存未命中 → 创建 bio → 提交到请求队列
  → I/O 调度器合并/排序 → 设备驱动执行 → DMA 传输
  → 中断通知完成 → 回调函数处理 → 唤醒等待进程
```

### 3.4 I/O 调度器（Elevator）

I/O 调度器的目标：**减少磁盘寻道、合并相邻请求。**

```
无调度：
  请求顺序: [扇区100] [扇区50] [扇区200] [扇区80] [扇区150]
  → 磁头来回移动，性能差

有调度（排序后）：
  请求顺序: [扇区50] [扇区80] [扇区100] [扇区150] [扇区200]
  → 磁头顺序移动，性能好
```

Linux 的 I/O 调度器演进：

| 调度器 | 策略 | 适用场景 |
|--------|------|---------|
| Linus Elevator | 简单排序 | 早期 Linux |
| Deadline | 排序 + 饥饿防止 | 保证延迟 |
| CFQ (Completely Fair Queuing) | 按进程公平分配 I/O | 桌面/通用 |
| BFQ (Budget Fair Queuing) | CFQ 改进版 | 低延迟交互 |
| mq-deadline | 多队列版 Deadline | NVMe SSD |
| none | 不调度（直接传递） | NVMe（设备自己调度） |

**SSD 时代的变化**：SSD 没有寻道开销，I/O 调度器的排序和合并意义不大。现代 NVMe 设备通常使用 `none` 调度器——把调度交给设备固件。

### 3.5 中断处理：上半部与下半部

中断处理需要快速完成（否则会阻塞其他中断），但有些工作比较耗时。Linux 把中断处理分成两部分：

```c
// 上半部（Top Half）：硬中断处理
// → 立即执行，时间极短
// → 只做最紧急的工作：确认中断、调度下半部
irqreturn_t disk_irq_handler(int irq, void *dev_id)
{
    // 1. 确认中断
    u32 status = readl(dev->reg_base + STATUS_REG);
    writel(status, dev->reg_base + STATUS_REG);  // 清中断

    // 2. 调度下半部
    schedule_work(&dev->work);  // 或 tasklet_schedule()

    return IRQ_HANDLED;
}

// 下半部（Bottom Half）：延迟处理
// → 在稍后执行，可以睡眠
// → 做耗时的工作：处理数据、唤醒进程
void disk_work_handler(struct work_struct *work)
{
    struct disk_dev *dev = container_of(work, struct disk_dev, work);

    // 处理完成的 I/O 请求
    struct request *req = dev->current_req;
    blk_mq_complete_request(req);

    // 唤醒等待的进程
    wake_up(&dev->wait_queue);
}
```

**设计哲学：分离紧急和非紧急工作——硬中断只做最少的必要工作，耗时操作推迟到下半部。**

下半部的三种机制：

| 机制 | 执行上下文 | 能否睡眠 | 适用场景 |
|------|-----------|---------|---------|
| SoftIRQ | 软中断上下文 | 不能 | 极高性能需求（网络、定时器） |
| Tasklet | 软中断上下文 | 不能 | 大多数中断下半部 |
| Workqueue | 内核线程 | 能 | 需要睡眠的操作（磁盘 I/O） |

### 3.6 设备驱动模型

```c
// 设备驱动注册（简化）
struct file_operations simple_fops = {
    .owner = THIS_MODULE,
    .read = simple_read,
    .write = simple_write,
    .open = simple_open,
    .release = simple_release,
    .poll = simple_poll,
};

int simple_init(void)
{
    // 注册字符设备
    int major = register_chrdev(0, "simple", &simple_fops);
    
    // 创建设备类和设备节点
    struct class *cls = class_create("simple");
    device_create(cls, NULL, MKDEV(major, 0), NULL, "simple");
    
    return 0;
}

ssize_t simple_read(struct file *filp, char __user *buf, size_t count, loff_t *pos)
{
    // 从设备读取数据
    // 可以使用 copy_to_user 把内核数据拷贝到用户空间
    int bytes_read = 0;
    while (count > 0) {
        put_user(*(dev_buffer + *pos), buf);
        (*pos)++;
        buf++;
        count--;
        bytes_read++;
    }
    return bytes_read;
}
```

**设备驱动的设计哲学：驱动是"适配器"——把硬件特定的接口适配到 OS 的统一接口。**

---

## 四、Trade-offs：I/O 设计的关键权衡

### 4.1 同步 vs 异步 I/O

| 方案 | 优点 | 缺点 |
|------|------|------|
| 同步 I/O | 简单、易理解 | 进程阻塞等待、线程资源浪费 |
| 异步 I/O | 不阻塞、高并发 | 编程复杂、错误处理困难 |

**Linux 的异步 I/O 演进**：
- POSIX AIO（glibc 实现）：用户态线程模拟，不是真正的异步
- io_uring（Linux 5.1+）：真正的内核级异步 I/O

io_uring 的设计：

```
用户和内核共享两个环形缓冲区：
  - Submission Queue (SQ)：用户提交 I/O 请求
  - Completion Queue (CQ)：内核通知 I/O 完成

用户提交请求 → 写 SQ → 内核消费 SQ → 执行 I/O → 写 CQ → 用户读取 CQ

全程不需要 syscall（除非 SQ 满了需要通知内核）
```

### 4.2 缓冲策略

| 策略 | 描述 | 适用场景 |
|------|------|---------|
| 无缓冲 | 直接读写设备 | 调试、特殊设备 |
| 内核缓冲 | 页缓存 | 普通文件 I/O |
| 用户缓冲 | 用户态缓冲区 | stdio（fread/fwrite） |
| 双缓冲 | 内核 + 用户 | 数据库 |

### 4.3 中断 vs 轮询

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 中断 | CPU 不浪费在等待上 | 中断开销、中断风暴 | 低频率 I/O |
| 轮询 | 无中断开销 | CPU 浪费 | 高频率 I/O（NVMe） |
| 混合 | 先轮询一段时间，超时后切换中断 | 兼顾两者 | 现代高速设备 |

**NVMe 的问题**：SSD 速度太快，每个 I/O 完成都发中断会导致**中断风暴**。解决方案：中断合并（多个完成合并为一个中断）或轮询模式。

---

## 五、Real-world Analysis：Linux I/O 源码

### 5.1 块设备请求的完整流程

```c
// submit_bio → blk_mq_submit_bio → 设备驱动

// block/blk-core.c（简化）
void submit_bio(struct bio *bio)
{
    blk_mq_submit_bio(bio);
}

// block/blk-mq.c（简化）
void blk_mq_submit_bio(struct bio *bio)
{
    struct request_queue *q = bio->bi_bdev->bd_queue;
    
    // 1. 从 SQ 分配请求
    struct request *rq = blk_mq_alloc_request(q, bio->bi_opf, ...);
    
    // 2. 把 bio 添加到请求
    blk_mq_bio_to_request(rq, bio);
    
    // 3. I/O 调度器插入（如果配置了调度器）
    if (q->elevator) {
        elv_insert(q, rq, ELEVATOR_INSERT_SORT);
    } else {
        // 无调度器：直接提交
        blk_mq_run_hw_queue(hctx, true);
    }
}
```

### 5.2 epoll — 高效的 I/O 多路复用

```c
// fs/eventpoll.c（简化）
struct eventpoll {
    struct rb_root_cached rbr;     // 红黑树（存储所有注册的 fd）
    struct list_head rdllist;      // 就绪链表（有事件发生的 fd）
    wait_queue_head_t wq;          // 等待队列
    // ...
};

// epoll_ctl：注册 fd
int do_epoll_ctl(int epfd, int op, int fd, struct epoll_event *epds)
{
    struct eventpoll *ep = ...;
    
    if (op == EPOLL_CTL_ADD) {
        // 在红黑树中插入新节点
        struct epitem *epi = ep_insert(ep, epds, tf.file, fd, 1);
    }
}

// epoll_wait：等待事件
int do_epoll_wait(int epfd, struct epoll_event __user *events, int maxevents)
{
    struct eventpoll *ep = ...;
    
    // 1. 检查就绪链表
    if (!list_empty(&ep->rdllist)) {
        // 有就绪事件，直接返回
        ep_send_events(ep, events, maxevents);
        return;
    }
    
    // 2. 没有就绪事件，睡眠等待
    wait_event_interruptible(ep->wq, !list_empty(&ep->rdllist));
    
    // 3. 被唤醒后，收集就绪事件
    ep_send_events(ep, events, maxevents);
}
```

**epoll vs select/poll 的关键区别**：

| 特性 | select | poll | epoll |
|------|--------|------|-------|
| 数据结构 | 位图 | 链表 | 红黑树 + 就绪链表 |
| 复杂度 | O(n) | O(n) | O(1)（就绪事件） |
| fd 数量限制 | 1024 | 无限制 | 无限制 |
| 每次调用 | 全量拷贝 fd 集 | 全量拷贝 fd 集 | 只拷贝就绪的 fd |
| 内核检查 | 遍历所有 fd | 遍历所有 fd | 只检查就绪链表 |

**epoll 的设计哲学：用红黑树管理注册的 fd（插入/删除 O(log n)），用就绪链表管理有事件的 fd（返回 O(1)）——把"关注哪些 fd"和"哪些 fd 有事件"分离。**

---

## 六、Hands-on Lab：lab06-io

### 实验1：Python I/O 调度模拟器

```python
# src/simulators/io_scheduler_sim.py
import heapq
from collections import deque

class IOSchedulerSimulator:
    """模拟不同的 I/O 调度算法"""
    
    def __init__(self, disk_size=1000):
        self.disk_size = disk_size
        self.current_position = 0
        self.requests = []
    
    def add_request(self, sector):
        self.requests.append(sector)
    
    def fifo(self):
        """先来先服务"""
        seq = list(self.requests)
        total_seek = 0
        pos = self.current_position
        for req in seq:
            total_seek += abs(req - pos)
            pos = req
        return seq, total_seek
    
    def sstf(self):
        """最短寻道时间优先"""
        remaining = list(self.requests)
        seq = []
        total_seek = 0
        pos = self.current_position
        while remaining:
            # 找最近的请求
            closest = min(remaining, key=lambda r: abs(r - pos))
            total_seek += abs(closest - pos)
            pos = closest
            seq.append(closest)
            remaining.remove(closest)
        return seq, total_seek
    
    def scan(self, direction=1):
        """电梯算法：向一个方向走到头，再反向"""
        remaining = sorted(self.requests)
        seq = []
        total_seek = 0
        pos = self.current_position
        
        if direction == 1:  # 向上
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
        else:  # 向下
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
        """循环扫描：到头后跳回起点"""
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
        # 跳回起点
        if down:
            total_seek += pos  # 回到0
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
    
    seq, seek = sim.fifo()
    print(f"FIFO:  sequence={seq}, total_seek={seek}")
    
    seq, seek = sim.sstf()
    print(f"SSTF:  sequence={seq}, total_seek={seek}")
    
    seq, seek = sim.scan(direction=1)
    print(f"SCAN:  sequence={seq}, total_seek={seek}")
    
    seq, seek = sim.cscan(direction=1)
    print(f"CSCAN: sequence={seq}, total_seek={seek}")
```

### 实验2：Python 中断处理模拟

```python
# src/simulators/interrupt_sim.py
import heapq
import random

class InterruptSimulator:
    """模拟中断处理的上半部/下半部机制"""
    
    def __init__(self):
        self.pending_interrupts = []
        self.bottom_half_queue = []
        self.current_time = 0
        self.stats = {"top_half": 0, "bottom_half": 0, "deferred": 0}
    
    def raise_interrupt(self, irq, priority=0):
        """设备发出中断"""
        heapq.heappush(self.pending_interrupts, (self.current_time, priority, irq))
    
    def top_half(self, irq):
        """上半部：快速处理"""
        self.stats["top_half"] += 1
        # 只做最紧急的工作：确认中断，调度下半部
        self.bottom_half_queue.append(irq)
        return 1  # 耗时1个时间单位
    
    def bottom_half(self, irq):
        """下半部：耗时处理"""
        self.stats["bottom_half"] += 1
        # 模拟耗时工作
        return random.randint(5, 20)
    
    def run(self, duration=100):
        for _ in range(duration):
            self.current_time += 1
            
            # 随机产生中断
            if random.random() < 0.3:
                irq = random.choice(["disk", "network", "keyboard", "timer"])
                self.raise_interrupt(irq)
            
            # 处理中断（上半部）
            while self.pending_interrupts and self.pending_interrupts[0][0] <= self.current_time:
                _, _, irq = heapq.heappop(self.pending_interrupts)
                self.top_half(irq)
            
            # 处理下半部（如果当前不在中断上下文）
            if self.bottom_half_queue and random.random() < 0.5:
                irq = self.bottom_half_queue.pop(0)
                self.bottom_half(irq)
        
        print(f"Stats: {self.stats}")

if __name__ == "__main__":
    sim = InterruptSimulator()
    sim.run(duration=200)
```

### 进阶实验

- 实现一个简单的字符设备驱动模块（用 QEMU + 最小 Linux 测试）
- 模拟 io_uring 的环形缓冲区机制
- 实现 epoll 的红黑树 + 就绪链表模拟

---

## 参考资源

- Linux 源码 `block/` — 块设备层
- Linux 源码 `drivers/` — 设备驱动
- Linux 源码 `fs/eventpoll.c` — epoll 实现
- Linux 源码 `kernel/irq/` — 中断管理
- *Linux Device Drivers* (Corbet et al.) — 设备驱动开发的经典教材
- *Understanding the Linux Kernel* Ch.6 — I/O 架构
- io_uring 文档：https://kernel.dk/io_uring.pdf