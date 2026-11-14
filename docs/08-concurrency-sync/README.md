# 08 - 并发与同步

> "Concurrency is not parallelism, but parallelism requires concurrency." — Rob Pike

---

## 一、Design Philosophy：并发与同步在解决什么问题？

### 1.1 核心问题

多核 CPU 和多任务环境下，多个执行流可能**同时**访问共享数据：

```c
// 经典的竞态条件
int balance = 1000;

// 线程 A：存款
void deposit(int amount) {
    balance += amount;  // 不是原子操作！
}

// 线程 B：取款
void withdraw(int amount) {
    balance -= amount;  // 不是原子操作！
}
```

`balance += amount` 看起来是一条语句，但在 CPU 上是三步：

```
1. LOAD  R1, balance      ; 从内存读取
2. ADD   R1, amount       ; 加法运算
3. STORE balance, R1      ; 写回内存
```

如果两个线程同时执行：

```
Thread A (deposit 100):    Thread B (withdraw 50):
  LOAD R1, balance (=1000)
                             LOAD R2, balance (=1000)
  ADD R1, 100 (=1100)
                             SUB R2, 50 (=950)
  STORE balance, 1100
                             STORE balance, 950    ← 覆盖了 A 的结果！

最终 balance = 950，应该是 1050。丢失了 100！
```

**并发控制的核心使命：保证多个执行流访问共享数据时的正确性。**

### 1.2 同步的两个层面

1. **互斥（Mutual Exclusion）**：同一时刻只有一个执行流可以访问共享数据
2. **有序（Ordering）**：多个执行流之间的执行顺序需要协调（如生产者-消费者）

### 1.3 并发 vs 并行

| 概念 | 定义 | 例子 |
|------|------|------|
| 并发（Concurrency） | 多个任务在逻辑上同时进行 | 单核上的时间片轮转 |
| 并行（Parallelism） | 多个任务在物理上同时执行 | 多核上同时运行 |

**并发是设计问题，并行是执行方式。** 并发程序可以在单核上运行（通过时间片轮转），也可以在多核上运行（真正的并行）。

---

## 二、Historical Evolution：同步机制的演进

### 2.1 禁用中断（最原始的方法）

单核系统上最简单的同步方法：禁用中断。

```c
// 禁用中断实现临界区
unsigned long flags;
local_irq_save(flags);    // 保存当前中断状态并禁用中断
// 临界区：操作共享数据
balance += amount;
local_irq_restore(flags); // 恢复中断状态
```

**优点**：简单、在单核上完全有效。
**缺点**：
- 多核上无效（其他核心的中断不受影响）
- 禁用中断时间过长会导致系统响应延迟
- 在用户态不可用（需要特权级）

### 2.2 原子指令

CPU 提供的原子操作指令：

```asm
; x86 的原子指令

; 1. 原子加
LOCK ADD [balance], 100    ; LOCK 前缀保证原子性

; 2. 比较并交换（CAS - Compare And Swap）
LOCK CMPXCHG [ptr], new_val
; 如果 [ptr] == expected，则 [ptr] = new_val
; 否则不动
; ZF 标志指示是否成功

; 3. 交换
LOCK XCHG [ptr], reg       ; 原子交换
```

**LOCK 前缀的工作原理**：在多核系统上，LOCK 前缀会锁定缓存行（cache line lock），确保该缓存行在操作期间不被其他核心修改。现代 CPU 使用缓存一致性协议（MESI）实现，不需要真正锁总线。

### 2.3 自旋锁（Spinlock）

自旋锁是最基础的锁机制——如果锁被占用，就反复检查（"自旋"）直到锁可用：

```c
// 简化的自旋锁实现
typedef struct {
    volatile int locked;
} spinlock_t;

void spin_lock(spinlock_t *lock) {
    while (__sync_lock_test_and_set(&lock->locked, 1)) {
        // 锁被占用，自旋等待
        // x86 上使用 PAUSE 指令减少功耗
        __asm__ volatile("pause");
    }
}

void spin_unlock(spinlock_t *lock) {
    __sync_lock_release(&lock->locked);
}
```

Linux 的实际实现更复杂——使用 ticket lock 或 MCS lock 来保证公平性：

```c
// Ticket Spinlock（简化）
typedef struct {
    volatile unsigned int next_ticket;  // 下一个发放的号码
    volatile unsigned int owner_ticket; // 当前持有者的号码
} ticket_lock_t;

void ticket_lock(ticket_lock_t *lock) {
    unsigned int my_ticket = __sync_fetch_and_add(&lock->next_ticket, 1);
    while (lock->owner_ticket != my_ticket) {
        __asm__ volatile("pause");
    }
}

void ticket_unlock(ticket_lock_t *lock) {
    __sync_fetch_and_add(&lock->owner_ticket, 1);
}
```

**Ticket lock 的设计哲学**：像银行排队取号——先到先服务，避免某个线程长期得不到锁（饥饿）。

### 2.4 信号量与互斥锁（Mutex）

自旋锁的问题是：如果等待时间长，CPU 在自旋上浪费大量时间。

信号量/互斥锁的解决方案：**如果锁被占用，当前线程进入睡眠，让出 CPU。**

```c
// 简化的信号量实现
typedef struct {
    int count;              // 可用资源数
    spinlock_t lock;        // 保护 count 的自旋锁
    wait_queue_head_t wait; // 等待队列
} semaphore_t;

void sem_wait(semaphore_t *sem) {
    spin_lock(&sem->lock);
    if (sem->count > 0) {
        sem->count--;       // 获取资源
        spin_unlock(&sem->lock);
    } else {
        // 没有资源，进入睡眠
        add_to_wait_queue(&sem->wait, current);
        set_current_state(TASK_INTERRUPTIBLE);
        spin_unlock(&sem->lock);
        schedule();         // 让出 CPU
        // 被唤醒后继续
    }
}

void sem_post(semaphore_t *sem) {
    spin_lock(&sem->lock);
    sem->count++;
    wake_up(&sem->wait);    // 唤醒一个等待者
    spin_unlock(&sem->lock);
}
```

**自旋锁 vs 互斥锁的选择**：

| 特性 | Spinlock | Mutex |
|------|----------|-------|
| 等待方式 | 忙等待（自旋） | 睡眠等待 |
| 适用场景 | 短临界区、不能睡眠 | 长临界区、可以睡眠 |
| 上下文 | 中断上下文可用 | 只能进程上下文 |
| 开销 | 无调度开销 | 两次上下文切换 |

**设计哲学：短临界区用自旋锁（避免调度开销），长临界区用互斥锁（避免 CPU 浪费）。**

### 2.5 RCU — Read-Copy-Update

RCU 是 Linux 最独特的同步机制，用于读多写少的场景：

```
传统方式（读写锁）：
  读者：获取读锁 → 读数据 → 释放读锁
  写者：获取写锁 → 修改数据 → 释放写锁
  问题：写者必须等待所有读者完成

RCU 方式：
  读者：不需要任何锁！直接读！
  写者：创建数据的副本 → 修改副本 → 原子替换指针 → 等待旧读者完成 → 释放旧数据
```

```
初始状态：
  ptr → [Data A]

读者1 开始读：读取 ptr → [Data A]
写者修改：
  1. 创建副本 [Data B]
  2. 修改 [Data B]
  3. ptr → [Data B]（原子替换）
  4. 等待读者1 完成（它还在读 [Data A]）
  5. 读者1 完成 → 释放 [Data A]

新读者：读取 ptr → [Data B]
```

**RCU 的设计哲学：读路径零开销——读者不需要任何同步操作，代价是写路径更复杂（需要复制和延迟回收）。**

RCU 的关键挑战：**如何知道所有旧读者已经完成？**

Linux 的解决方案：**宽限期（Grace Period）**——所有当前在 CPU 上运行的线程都至少经历了一次上下文切换后，可以确保没有旧读者还在访问旧数据。

```c
// RCU 的核心 API
rcu_read_lock();      // 进入 RCU 读临界区（实际上什么都不做！）
ptr = rcu_dereference(p);  // 读取受 RCU 保护的指针
// 使用 ptr...
rcu_read_unlock();    // 退出 RCU 读临界区

// 写者
new_ptr = create_new_data();
old_ptr = rcu_dereference_protected(p, ...);
rcu_assign_pointer(p, new_ptr);  // 原子替换指针
synchronize_rcu();    // 等待宽限期（所有旧读者完成）
kfree(old_ptr);       // 安全释放旧数据
```

---

## 三、Core Mechanism：Linux 的同步原语

### 3.1 同步原语全景

```
按临界区长度和上下文选择：

┌──────────────────────────────────────────────────┐
│  临界区长度                                        │
│  短 ←────────────────────────────────────→ 长     │
│                                                    │
│  中断上下文:  spinlock_irqsave                     │
│  软中断上下文: spinlock_bh                          │
│  进程上下文（短）: spinlock                          │
│  进程上下文（长）: mutex / semaphore                 │
│  读多写少:    rwlock / RCU                          │
│  简单计数器:  atomic_t / percpu                     │
└──────────────────────────────────────────────────┘
```

### 3.2 spinlock 的变体

Linux 提供多种 spinlock 变体，适应不同上下文：

| 变体 | 禁用中断 | 禁用下半部 | 适用场景 |
|------|---------|-----------|---------|
| `spin_lock()` | 否 | 否 | 进程上下文，短临界区 |
| `spin_lock_irqsave()` | 是 | 否 | 中断可能访问的数据 |
| `spin_lock_bh()` | 否 | 是 | 软中断可能访问的数据 |

**为什么需要禁用中断？** 如果在持锁期间发生中断，中断处理程序可能尝试获取同一把锁 → 死锁。

```c
// 正确用法：在中断可能访问的数据上使用 irqsave 版本
unsigned long flags;
spin_lock_irqsave(&my_lock, flags);
// 临界区
spin_unlock_irqrestore(&my_lock, flags);
```

### 3.3 mutex 的实现

```c
// include/linux/mutex.h
struct mutex {
    atomic_long_t owner;          // 持有者的 task_struct 指针
    struct optimistic_spin_queue osq; // 乐观自旋队列
    struct list_head wait_list;   // 等待队列
    // ...
};

// kernel/locking/mutex.c（简化）
void __mutex_lock_slowpath(struct mutex *lock)
{
    // 1. 乐观自旋：如果持有者正在运行，可能很快释放
    if (mutex_optimistic_spin(lock))
        return;  // 自旋获取成功！

    // 2. 乐观自旋失败，加入等待队列并睡眠
    add_to_wait_queue(&lock->wait_list, current);
    set_current_state(TASK_UNINTERRUPTIBLE);
    
    while (!mutex_trylock(lock)) {
        schedule();  // 让出 CPU
        set_current_state(TASK_UNINTERRUPTIBLE);
    }
    
    remove_from_wait_queue(&lock->wait_list, current);
}
```

**乐观自旋（Optimistic Spinning）的设计哲学**：如果锁的持有者正在另一个核心上运行，它可能很快释放锁——此时自旋等待比睡眠+唤醒更快（避免了两次上下文切换的开销）。

### 3.4 读写锁（rwlock）

读写锁允许多个读者同时访问，但写者独占：

```c
// 简化的读写锁
typedef struct {
    atomic_t readers;     // 当前读者数
    int writer;           // 是否有写者
    spinlock_t lock;      // 保护内部状态
} rwlock_t;

void read_lock(rwlock_t *rw) {
    spin_lock(&rw->lock);
    while (rw->writer) {  // 有写者在等待
        spin_unlock(&rw->lock);
        // 等待...
        spin_lock(&rw->lock);
    }
    atomic_inc(&rw->readers);
    spin_unlock(&rw->lock);
}

void write_lock(rwlock_t *rw) {
    spin_lock(&rw->lock);
    while (rw->writer || atomic_read(&rw->readers) > 0) {
        spin_unlock(&rw->lock);
        // 等待...
        spin_lock(&rw->lock);
    }
    rw->writer = 1;
    spin_unlock(&rw->lock);
}
```

**读写锁的问题**：写者可能饥饿——只要有读者在，写者就必须等待。如果读者持续到来，写者永远得不到机会。

**Linux 的改进**：读写信号量（rwsem）支持写者优先——当写者在等待时，新读者不能获取锁。

### 3.5 per-CPU 变量

对于每个 CPU 独立的数据，不需要任何锁：

```c
// 定义 per-CPU 变量
DEFINE_PER_CPU(int, counter);

// 访问（需要禁用抢占）
int cpu = get_cpu();  // 禁用抢占并获取 CPU 编号
this_cpu_inc(counter); // 当前 CPU 的 counter++
put_cpu();             // 恢复抢占
```

**设计哲学：避免共享——如果数据不需要共享，就不需要同步。** per-CPU 变量让每个 CPU 有自己的副本，只在需要全局统计时才汇总。

### 3.6 内存屏障（Memory Barrier）

CPU 和编译器都会重排序指令以提高性能，但在并发场景下可能导致问题：

```c
// 经典的消息传递问题
int data = 0;
int ready = 0;

// 线程 A（生产者）
data = 42;         // (1)
ready = 1;         // (2)

// 线程 B（消费者）
if (ready)         // (3)
    assert(data == 42);  // (4) 可能失败！
```

CPU 可能重排序 (1) 和 (2)，导致消费者看到 `ready=1` 但 `data` 还是 0。

```c
// 使用内存屏障
// 线程 A
data = 42;
smp_wmb();         // 写屏障：确保 (1) 在 (2) 之前对其他 CPU 可见
ready = 1;

// 线程 B
if (ready) {
    smp_rmb();     // 读屏障：确保 (3) 在 (4) 之前执行
    assert(data == 42);  // 保证成功
}
```

**内存屏障的类型**：

| 屏障 | 作用 | 实现（x86） |
|------|------|------------|
| `smp_wmb()` | 写屏障：之前的写操作对其他 CPU 可见 | `sfence`（实际上 x86 强序模型不需要） |
| `smp_rmb()` | 读屏障：之后的读操作看到最新数据 | `lfence`（实际上 x86 强序模型不需要） |
| `smp_mb()` | 全屏障：读写都有序 | `mfence` |
| `smp_store_release()` | 释放语义：之前的读写都对其他 CPU 可见 | `mov` + 隐含屏障 |
| `smp_load_acquire()` | 获取语义：之后的读写都看到最新数据 | `mov` + 隐含屏障 |

**x86 是强序模型（TSO）**——写操作不会重排序，读操作可以重排序。所以 `smp_wmb()` 在 x86 上是空操作。但 ARM/POWER 是弱序模型，需要真正的屏障指令。

**设计哲学：用 acquire/release 语义替代显式屏障——更安全、更可移植。**

---

## 四、经典并发问题

### 4.1 死锁（Deadlock）

死锁的四个必要条件（Coffman 条件）：
1. **互斥**：资源只能被一个进程占有
2. **持有并等待**：持有资源的同时等待另一个资源
3. **不可剥夺**：资源不能被强制夺走
4. **循环等待**：多个进程形成等待环

```c
// 死锁示例
void thread_a() {
    lock(lock1);
    lock(lock2);  // 如果 thread_b 已经持有 lock2，死锁！
    // ...
    unlock(lock2);
    unlock(lock1);
}

void thread_b() {
    lock(lock2);
    lock(lock1);  // 如果 thread_a 已经持有 lock1，死锁！
    // ...
    unlock(lock1);
    unlock(lock2);
}
```

**解决方案：锁排序**——所有线程按相同顺序获取锁：

```c
// 正确：总是先 lock1 再 lock2
void thread_a() {
    lock(lock1);
    lock(lock2);
    // ...
    unlock(lock2);
    unlock(lock1);
}

void thread_b() {
    lock(lock1);  // 先 lock1！
    lock(lock2);  // 再 lock2！
    // ...
    unlock(lock2);
    unlock(lock1);
}
```

### 4.2 生产者-消费者

```c
// 使用信号量解决生产者-消费者问题
sem_t empty;   // 空槽数（初始 = N）
sem_t full;    // 满槽数（初始 = 0）
mutex_t mutex; // 保护缓冲区

void producer() {
    while (1) {
        item = produce();
        sem_wait(&empty);    // 等待空槽
        mutex_lock(&mutex);
        buffer_add(item);
        mutex_unlock(&mutex);
        sem_post(&full);     // 增加满槽
    }
}

void consumer() {
    while (1) {
        sem_wait(&full);     // 等待满槽
        mutex_lock(&mutex);
        item = buffer_remove();
        mutex_unlock(&mutex);
        sem_post(&empty);    // 增加空槽
        consume(item);
    }
}
```

### 4.3 哲学家就餐

```
5 个哲学家，5 把叉子，每个哲学家需要两把叉子才能吃饭。

     Philosopher 0
    / Fork 0    Fork 1 \
Philosopher 4          Philosopher 1
    \ Fork 4    Fork 2 /
     Philosopher 3 -- Fork 3 -- Philosopher 2
```

**简单方案（会死锁）**：每个哲学家先拿左叉子，再拿右叉子 → 如果所有人同时拿左叉子，死锁。

**解决方案**：
1. 限制人数：最多 4 个哲学家同时尝试拿叉子
2. 奇偶规则：奇数号哲学家先拿右叉子，偶数号先拿左叉子
3. 一次性获取：要么同时拿到两把叉子，要么都不拿

---

## 五、Trade-offs：同步设计的关键权衡

### 5.1 锁粒度

| 粒度 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 粗粒度（一把大锁） | 简单、无死锁风险 | 并行度低、竞争激烈 | 早期 Linux BKL |
| 细粒度（多把小锁） | 并行度高、竞争少 | 复杂、死锁风险 | 现代 Linux |
| 无锁（原子操作/RCU） | 极致性能 | 实现极复杂、适用场景有限 | 热路径数据结构 |

**Linux 的演进**：从 Big Kernel Lock（一把锁锁整个内核）→ 细粒度锁 → RCU（读路径无锁）。

### 5.2 公平性 vs 性能

| 方案 | 公平性 | 性能 | 实现 |
|------|--------|------|------|
| 不公平锁 | 可能饥饿 | 高（无排队开销） | 简单自旋锁 |
| 公平锁（ticket） | 先到先得 | 中（排队开销） | ticket lock |
| RCU | N/A（读无锁） | 最高（读路径） | RCU |

### 5.3 乐观 vs 悲观

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 悲观（先锁再操作） | 安全、简单 | 竞争激烈时开销大 | 写多场景 |
| 乐观（先操作再验证） | 竞争少时极快 | 竞争多时重试开销大 | 读多写少场景 |

**乐观并发控制（OCC）的典型实现**：CAS 循环

```c
// 乐观更新：用 CAS 实现原子操作
void atomic_add(int *ptr, int val) {
    int old, new;
    do {
        old = *ptr;
        new = old + val;
    } while (!__sync_bool_compare_and_swap(ptr, old, new));
    // 如果 ptr 仍然是 old，则设为 new；否则重试
}
```

---

## 六、Real-world Analysis：Linux 同步源码

### 6.1 spinlock 的实际实现

```c
// include/linux/spinlock.h
static __always_inline void spin_lock(spinlock_t *lock)
{
    raw_spin_lock(&lock->rlock);
}

// kernel/locking/spinlock.c
void __raw_spin_lock(raw_spinlock_t *lock)
{
    preempt_disable();           // 禁用抢占
    spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
    do_raw_spin_lock(lock);      // 实际获取锁
}

// arch/x86/include/asm/qspinlock.h（简化）
static __always_inline void queued_spin_lock(struct qspinlock *lock)
{
    // 1. 快速路径：如果锁空闲，直接获取
    if (likely(atomic_try_cmpxchg_acquire(&lock->val, &val, _Q_LOCKED_VAL)))
        return;
    
    // 2. 慢速路径：加入等待队列
    queued_spin_lock_slowpath(lock, val);
}
```

**qspinlock（MCS lock 的队列版本）**：当锁竞争激烈时，每个 CPU 在自己的本地变量上自旋，而不是在全局锁变量上自旋——减少缓存行争用。

### 6.2 RCU 在内核中的使用

```c
// 读路径（极热路径，如网络包处理）
rcu_read_lock();
struct foo *p = rcu_dereference(global_ptr);
// 使用 p...
rcu_read_unlock();

// 写路径
struct foo *new = kmalloc(sizeof(*new), GFP_KERNEL);
new->field = new_value;

struct foo *old = rcu_dereference_protected(global_ptr, ...);
rcu_assign_pointer(global_ptr, new);  // 原子替换

synchronize_rcu();  // 等待所有读者完成
kfree(old);         // 安全释放
```

**RCU 在 Linux 中的关键应用**：
- dentry 缓存——路径查找极频繁，修改极少
- 路由表——查路由极频繁，路由更新极少
- PID 查找——查找极频繁，进程创建/销毁相对少

---

## 七、Hands-on Lab：lab07-lock

### 实验1：Python 并发问题模拟

```python
# src/simulators/concurrency_sim.py
import threading
import time

class BankAccount:
    def __init__(self, balance=1000):
        self.balance = balance
    
    # 有竞态条件的版本
    def unsafe_deposit(self, amount):
        temp = self.balance
        time.sleep(0.0001)  # 模拟上下文切换
        self.balance = temp + amount
    
    def unsafe_withdraw(self, amount):
        temp = self.balance
        time.sleep(0.0001)
        self.balance = temp - amount
    
    # 用锁保护的版本
    def safe_deposit(self, amount, lock):
        with lock:
            self.balance += amount
    
    def safe_withdraw(self, amount, lock):
        with lock:
            self.balance -= amount

def test_unsafe():
    account = BankAccount(1000)
    threads = []
    for _ in range(100):
        t = threading.Thread(target=account.unsafe_deposit, args=(10,))
        threads.append(t)
    for _ in range(100):
        t = threading.Thread(target=account.unsafe_withdraw, args=(10,))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Unsafe: balance = {account.balance} (expected 1000)")

def test_safe():
    account = BankAccount(1000)
    lock = threading.Lock()
    threads = []
    for _ in range(100):
        t = threading.Thread(target=account.safe_deposit, args=(10, lock))
        threads.append(t)
    for _ in range(100):
        t = threading.Thread(target=account.safe_withdraw, args=(10, lock))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Safe: balance = {account.balance} (expected 1000)")

if __name__ == "__main__":
    test_unsafe()
    test_safe()
```

### 实验2：C 实现自旋锁和 CAS

```c
// src/mini-kernel/locks.c
#include <stdio.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>

// 简单自旋锁
typedef struct {
    atomic_flag locked;
} spinlock_t;

void spin_lock(spinlock_t *lock) {
    while (atomic_flag_test_and_set_explicit(&lock->locked,
                                              memory_order_acquire)) {
        // 自旋等待
    }
}

void spin_unlock(spinlock_t *lock) {
    atomic_flag_clear_explicit(&lock->locked, memory_order_release);
}

// CAS 实现的原子计数器
typedef struct {
    int value;
} atomic_counter_t;

void counter_add(atomic_counter_t *c, int val) {
    int old, new;
    do {
        old = atomic_load(&c->value);
        new = old + val;
    } while (!__sync_bool_compare_and_swap(&c->value, old, new));
}

// 测试
spinlock_t lock = {0};
atomic_counter_t counter = {0};

void *worker(void *arg) {
    for (int i = 0; i < 100000; i++) {
        spin_lock(&lock);
        counter.value++;
        spin_unlock(&lock);
    }
    return NULL;
}

void *cas_worker(void *arg) {
    for (int i = 0; i < 100000; i++) {
        counter_add(&counter, 1);
    }
    return NULL;
}

int main() {
    pthread_t threads[4];
    
    printf("=== Spinlock test ===\n");
    counter.value = 0;
    for (int i = 0; i < 4; i++)
        pthread_create(&threads[i], NULL, worker, NULL);
    for (int i = 0; i < 4; i++)
        pthread_join(threads[i], NULL);
    printf("Result: %d (expected 400000)\n", counter.value);
    
    printf("\n=== CAS test ===\n");
    counter.value = 0;
    for (int i = 0; i < 4; i++)
        pthread_create(&threads[i], NULL, cas_worker, NULL);
    for (int i = 0; i < 4; i++)
        pthread_join(threads[i], NULL);
    printf("Result: %d (expected 400000)\n", counter.value);
    
    return 0;
}
```

### 实验3：Python 死锁模拟

```python
# src/simulators/deadlock_sim.py
import threading
import time

class Philosopher:
    def __init__(self, name, left_fork, right_fork):
        self.name = name
        self.left_fork = left_fork
        self.right_fork = right_fork
    
    def dine(self):
        for _ in range(3):
            print(f"{self.name} thinking...")
            time.sleep(0.1)
            
            print(f"{self.name} picking up left fork")
            self.left_fork.acquire()
            time.sleep(0.1)
            
            print(f"{self.name} picking up right fork")
            if not self.right_fork.acquire(timeout=1.0):
                print(f"{self.name} couldn't get right fork, releasing left")
                self.left_fork.release()
                continue
            
            print(f"{self.name} eating!")
            time.sleep(0.1)
            
            self.right_fork.release()
            self.left_fork.release()
            print(f"{self.name} done eating")

def test_deadlock():
    """可能死锁的版本"""
    forks = [threading.Lock() for _ in range(5)]
    philosophers = [
        Philosopher(f"Philosopher {i}", forks[i], forks[(i+1) % 5])
        for i in range(5)
    ]
    
    threads = [threading.Thread(target=p.dine) for p in philosophers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    
    print("All philosophers done (or deadlocked)")

def test_no_deadlock():
    """不会死锁的版本：最后一个哲学家先拿右叉子"""
    forks = [threading.Lock() for _ in range(5)]
    philosophers = []
    for i in range(5):
        left = forks[i]
        right = forks[(i+1) % 5]
        if i == 4:  # 最后一个哲学家：先右后左
            philosophers.append(Philosopher(f"Philosopher {i}", right, left))
        else:
            philosophers.append(Philosopher(f"Philosopher {i}", left, right))
    
    threads = [threading.Thread(target=p.dine) for p in philosophers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    print("All philosophers done (no deadlock)")

if __name__ == "__main__":
    print("=== Deadlock-prone version ===")
    test_deadlock()
    print("\n=== Deadlock-free version ===")
    test_no_deadlock()
```

### 进阶实验

- 实现 ticket lock 并测试公平性
- 实现 RCU 模拟（读者无锁，写者复制+延迟释放）
- 用内存屏障解决消息传递问题
- 实现 per-CPU 计数器并汇总

---

## 参考资源

- Linux 源码 `kernel/locking/` — 所有同步原语实现
- Linux 源码 `include/linux/spinlock.h` — spinlock 接口
- Linux 源码 `include/linux/rcupdate.h` — RCU 接口
- *Operating Systems: Three Easy Points* — 并发章节（免费在线）
- *Understanding the Linux Kernel* Ch.5 — 内核同步
- *Is Parallel Programming Hard, And, If So, What Can You Do About It?* (Paul McKenney) — RCU 作者的免费书
- *The Art of Multiprocessor Programming* (Herlihy & Shavit) — 并发编程理论经典