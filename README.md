# OS Learning Journey

系统性学习操作系统底层原理与设计哲学的教学项目。

## 核心理念

**从零构建 + 逆向分析 + 算法模拟** 三位一体，理解 OS 每个组件**为什么这样设计**，而不仅仅是**怎样实现**。

## 学习路线图

| 阶段 | 主题 | 核心设计哲学问题 | 实践 |
|------|------|------------------|------|
| 0 | **设计哲学总论** | OS 的本质是什么？核心矛盾与权衡有哪些？ | 建立思维框架 |
| 1 | **启动与初始化** | 为什么需要 bootloader？BIOS→UEFI 的演进逻辑 | C+ASM 最小 bootloader |
| 2 | **进程与调度** | 为什么用"进程"抽象？调度算法的设计权衡 | Python 模拟 5 种调度 + C 上下文切换 |
| 3 | **内存管理** | 为什么要分层分配？碎片问题的本质 | C 实现 buddy allocator |
| 4 | **虚拟内存** | 页表为什么是多级的？TLB 的设计哲学 | Python 模拟页表翻译 + 页面置换 |
| 5 | **文件系统** | VFS 抽象的意义？inode vs fd 的设计逻辑 | C 实现 mini FS |
| 6 | **I/O 与设备驱动** | 为什么 I/O 要分层？中断 vs 轮询 vs DMA | Python 模拟 I/O 调度 |
| 7 | **系统调用** | user/kernel mode 为什么要隔离？ | C 实现 mini syscall |
| 8 | **并发与同步** | 锁的本质？spinlock vs mutex 的适用场景 | C 实现锁 + Python 模拟死锁 |

## 目录结构

```
os/
├── docs/          # 设计哲学与原理文档（每个主题深入到 Linux 源码级别）
├── src/
│   ├── mini-kernel/         # C 语言实现的 OS 核心组件简化版本
│   ├── simulators/          # Python OS 算法模拟器
│   └── reverse-engineering/ # 真实 Linux kernel 源码逆向分析
├── labs/          # 动手实验
└── notes/         # 个人学习笔记
```

## 文档格式

每个主题遵循统一结构：
1. **Design Philosophy** — 解决什么根本问题？为什么不能没有它？
2. **Historical Evolution** — Unix → Linux → 现代的演进逻辑
3. **Core Mechanism** — 数据结构与算法剖析（配代码片段）
4. **Trade-offs** — 性能 vs 简洁 vs 安全 vs 可扩展性
5. **Real-world Analysis** — Linux 内核源码真实实现解读
6. **Hands-on Lab** — 对应实验

## 快速开始

### 运行 Python 模拟器

```bash
python src/simulators/scheduler_sim.py      # 调度算法对比
python src/simulators/page_table_sim.py     # 页表翻译
python src/simulators/page_replacement_sim.py # 页面置换
python src/simulators/buddy_visualizer.py   # Buddy System
python src/simulators/io_scheduler_sim.py   # I/O 调度
python src/simulators/vfs_sim.py            # VFS 层次结构
python src/simulators/concurrency_sim.py    # 并发问题
python src/simulators/syscall_sim.py        # 系统调用分发
```

### 编译运行 C 实现

```bash
gcc src/mini-kernel/buddy.c -o buddy && ./buddy
gcc src/mini-kernel/context_switch.c -o context_switch && ./context_switch
gcc src/mini-kernel/locks.c -o locks -lpthread && ./locks
gcc src/mini-kernel/mini_fs.c -o mini_fs && ./mini_fs
```

## 技术栈

- **mini-kernel**: C 语言（与 Linux 源码一致，便于对照分析）
- **simulators**: Python（快速实验与可视化）
- **逆向分析**: Linux kernel source（主要参考 6.x 版本）

## 文档站

在线文档：[GitHub Pages](https://wanglh39.github.io/os/)