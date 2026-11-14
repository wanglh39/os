# 01 - 启动与初始化

> "The journey of a thousand miles begins with a single boot."

---

## 一、Design Philosophy：启动过程在解决什么问题？

### 1.1 核心矛盾

启动过程面临一个根本性的**鸡生蛋问题**：

- OS 代码存在磁盘上，但读取磁盘需要 OS 的文件系统驱动
- OS 需要运行在内存中，但加载代码到内存需要执行代码
- OS 需要 CPU 处于特定模式（保护模式/长模式），但切换模式需要执行代码

**解决方案：分阶段启动——每个阶段为下一个阶段准备环境。**

```
通电 → BIOS/UEFI → Bootloader → Kernel → Init
       (固件)      (过渡层)     (内核)    (用户态)
```

每个阶段的设计哲学：

| 阶段 | 能做什么 | 不能做什么 | 为下一阶段准备什么 |
|------|---------|-----------|-------------------|
| BIOS/UEFI | 硬件自检、读取第一个扇区 | 不理解文件系统 | 找到并执行 bootloader |
| Bootloader | 理解简单文件系统、切换 CPU 模式 | 不能管理进程/内存 | 加载内核到内存、传递参数 |
| Kernel | 初始化所有子系统 | 还没有用户进程 | 建立进程、内存、文件系统抽象 |
| Init | 启动用户服务 | 运行在 user mode | 完整的用户态环境 |

### 1.2 为什么不能一步到位？

因为**硬件的限制**和**复杂性的递进**：

1. CPU 通电后处于**实模式**（Real Mode），只能寻址 1MB 内存，没有内存保护
2. 实模式下无法运行现代 OS——需要切换到**保护模式**（32位）或**长模式**（64位）
3. 切换模式需要设置 GDT（全局描述符表）、页表等数据结构
4. 这些数据结构需要内存，但内存管理还没初始化
5. 所以必须**逐步建立**——先有最简单的内存布局，再建立更复杂的

**设计哲学：渐进式初始化——先建立最小可行环境，再逐步增强。**

---

## 二、Historical Evolution：从 BIOS 到 UEFI

### 2.1 BIOS 时代（1981-2010s）

BIOS（Basic Input/Output System）是 IBM PC 的遗产：

```
通电 → CPU 跳转到 0xFFFF0（BIOS 入口） → POST（自检） → 读取磁盘第一个扇区（512字节） → 执行
```

BIOS 的核心限制：
- **16位实模式**：只能寻址 1MB 内存
- **MBR 分区表**：最多 4 个主分区，最大 2TB 磁盘
- **512字节引导扇区**：太小了，连一个像样的文件系统驱动都放不下
- **没有网络启动**（后来通过 PXE 扩展）
- **串行初始化**：每个设备依次检测，启动慢

### 2.2 UEFI 时代（2010s-现在）

UEFI（Unified Extensible Firmware Interface）解决了 BIOS 的所有核心限制：

| 特性 | BIOS | UEFI |
|------|------|------|
| CPU 模式 | 16位实模式 | 直接进入 64位长模式 |
| 分区表 | MBR（4分区，2TB限制） | GPT（128分区，无限制） |
| 引导程序 | 512字节扇区 | EFI System Partition 上的 .efi 文件 |
| 文件系统 | 不支持 | 支持 FAT32（至少） |
| 网络 | PXE（有限） | 内置网络栈 |
| 初始化 | 串行 | 可并行 |
| 安全 | 无 | Secure Boot |

**为什么 UEFI 能直接进入 64 位模式？** 因为 UEFI 固件本身就是一个微型 OS，它在固件阶段就完成了 CPU 模式切换和基本内存初始化。

### 2.3 Secure Boot 的设计哲学

Secure Boot 解决的问题是：**如何确保启动链的每一步都是可信的？**

```
UEFI 固件 → 验证 bootloader 签名 → 验证 kernel 签名 → 验证内核模块签名
```

每一级验证下一级的签名，形成**信任链**。如果任何一级签名验证失败，启动中止。

**设计哲学：信任锚点 + 链式验证——从一个可信的根出发，逐步扩展信任范围。**

这是 OS 安全设计的核心模式，后面在系统调用和并发同步中还会看到类似的设计。

---

## 三、Core Mechanism：Linux 启动的完整流程

### 3.1 全景图

```
┌──────────────────────────────────────────────────────────────┐
│ 1. UEFI/BIOS                                                  │
│    - POST (Power-On Self-Test)                                │
│    - 初始化基本硬件                                            │
│    - 找到启动设备，加载 bootloader                             │
├──────────────────────────────────────────────────────────────┤
│ 2. Bootloader (GRUB)                                          │
│    - 读取内核镜像 (vmlinuz) 和 initramfs                      │
│    - 切换 CPU 到保护模式/长模式                                │
│    - 设置启动参数 (cmdline)                                    │
│    - 跳转到内核入口                                            │
├──────────────────────────────────────────────────────────────┤
│ 3. Kernel 早期初始化 (实模式/保护模式)                         │
│    - arch/x86/boot/ 下的代码                                   │
│    - setup.elf: 设置 GDT、切换到保护模式                       │
│    - compressed/head_64.S: 解压内核、切换到长模式              │
├──────────────────────────────────────────────────────────────┤
│ 4. Kernel 主初始化 (长模式)                                    │
│    - start_kernel() in init/main.c                            │
│    - 初始化所有子系统：内存、调度、中断、文件系统...            │
│    - 创建第一个进程 (idle/0)                                   │
├──────────────────────────────────────────────────────────────┤
│ 5. Init 进程                                                   │
│    - kernel_init() → 执行 /sbin/init (或 systemd)             │
│    - 启动用户态服务                                            │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 阶段详解

#### 阶段1：UEFI/BIOS

CPU 通电后，指令指针（RIP）被硬件设置为 `0xFFFF0`（BIOS）或 UEFI 固件入口。

BIOS 做的事：
```c
// 伪代码
void bios_main() {
    post();              // 硬件自检
    init_hardware();     // 初始化基本硬件（键盘、显示、磁盘控制器）
    
    // 读取磁盘第一个扇区（MBR）到 0x7C00
    read_sector(0, 0x7C00);
    
    // 跳转到 0x7C00 执行 bootloader
    ((void(*)())0x7C00)();
}
```

为什么是 `0x7C00`？这是 IBM PC BIOS 的历史决定——0x7C00 在 1MB 实模式地址空间的低端，留出了足够空间给 BIOS 数据区（0x400-0x500）和引导程序本身。

#### 阶段2：Bootloader（GRUB）

GRUB 的工作流程：

```
GRUB Stage 1 (446字节，在MBR中)
  → GRUB Stage 1.5 (在MBR后的扇区，理解文件系统)
    → GRUB Stage 2 (在文件系统中，完整功能)
      → 加载 vmlinuz + initramfs
      → 切换 CPU 模式
      → 跳转到内核入口
```

GRUB 传递给内核的关键信息：

```c
// Linux boot protocol 要求 bootloader 传递的结构
struct boot_params {
    // 命令行参数
    char *cmdline_ptr;           // 如 "root=/dev/sda1 ro quiet"
    
    // 内存布局信息
    struct e820_entry e820_map[]; // BIOS 提供的内存映射
    
    // 内核加载位置
    uint32_t code32_start;        // 内核入口地址
    
    // initramfs 位置
    uint32_t initrd_start;
    uint32_t initrd_size;
    
    // 显示模式信息
    // ...
};
```

**设计哲学：bootloader 和内核之间通过**结构化协议**通信，而不是硬编码。** 这使得不同的 bootloader（GRUB、systemd-boot、直接 UEFI 启动）都能启动同一个内核。

#### 阶段3：内核早期初始化

内核镜像 `vmlinuz` 实际上是**压缩的**。启动时先执行一小段解压代码：

```asm
// arch/x86/boot/compressed/head_64.S（简化）
startup_64:
    // 1. 设置基本环境
    leaq    _text(%rip), %rbp     // 获取内核加载地址
    
    // 2. 解压内核
    call    extract_kernel         // 解压 vmlinuz 到最终位置
    
    // 3. 跳转到解压后的内核入口
    jmp     startup_64            // 真正的内核入口
```

为什么内核要压缩？
- 减小磁盘占用和启动时 I/O 时间
- 现代解压速度远快于磁盘读取速度
- **权衡**：增加少量解压 CPU 时间，减少大量磁盘 I/O 时间

#### 阶段4：start_kernel() — 内核主初始化

这是整个启动过程中最重要的函数。位于 `init/main.c`：

```c
// init/main.c（简化版，展示关键调用顺序）
asmlinkage __visible void __init start_kernel(void)
{
    // === 阶段A：最小可行环境 ===
    set_task_stack_end_magic(&init_task);  // 初始化 init_task（PID 0）
    setup_arch(&command_line);             // 架构相关初始化（页表、GDT、IDT）
    mm_init_owner(&init_mm, &init_task);   // 初始化 init_mm（内核地址空间）
    
    // === 阶段B：内存管理 ===
    setup_per_cpu_areas();                 // per-CPU 数据区域
    build_all_zonelists(NULL);             // 初始化内存 zone（DMA/DMA32/NORMAL）
    page_alloc_init();                     // 页面分配器
    mm_init();                             // 内存管理子系统（slab, vmalloc 等）
    
    // === 阶段C：中断与调度 ===
    trap_init();                           // 异常/中断处理（IDT 设置）
    init_IRQ();                            // 硬件中断
    tick_init();                           // 时钟初始化
    timer_init();                          // 定时器子系统
    sched_init();                          // 调度器初始化
    
    // === 阶段D：控制台与文件系统 ===
    console_init();                        // 控制台（能看到启动日志了！）
    vfs_caches_init();                     // VFS 缓存（dentry、inode）
    rest_init();                           // 创建 init 进程，进入调度
}
```

**注意初始化顺序的设计逻辑**：

1. 先初始化**内存**——因为后面所有子系统都需要分配内存
2. 再初始化**中断**——因为设备初始化需要中断支持
3. 再初始化**调度器**——因为需要创建进程
4. 最后初始化**文件系统**——因为需要前述所有基础设施

**这不是随意的顺序，而是严格的依赖关系决定的。**

#### 阶段5：rest_init() — 从内核到用户态

```c
// init/main.c（简化）
noinline void __ref rest_init(void)
{
    // 创建 PID 1（init/systemd 进程）
    pid = kernel_thread(kernel_init, NULL, CLONE_FS);
    
    // PID 0 变成 idle 进程
    cpu_startup_entry(CPUHP_ONLINE);
}

static int __ref kernel_init(void *unused)
{
    // 等待设备初始化完成
    wait_for_completion(&kthreadd_done);
    
    // 尝试执行 init 程序
    if (!try_to_run_init_process("/sbin/init") ||
        !try_to_run_init_process("/etc/init") ||
        !try_to_run_init_process("/bin/init") ||
        !try_to_run_init_process("/bin/sh"))
        panic("No init found");
    
    return 0;
}
```

**关键设计决策**：

1. **PID 0 是 idle 进程**——当没有其他进程可运行时，CPU 执行 idle 进程（它只是循环执行 HLT 指令让 CPU 休眠）
2. **PID 1 是 init 进程**——所有用户进程的祖先，如果它死了，系统 panic
3. **init 的查找路径**——按顺序尝试多个路径，这是**容错设计**的体现

### 3.3 initramfs：为什么需要它？

内核启动时面临另一个鸡生蛋问题：

- 内核需要挂载根文件系统（rootfs）才能启动 init
- 但挂载 rootfs 需要文件系统驱动和磁盘驱动
- 这些驱动在 rootfs 里

**解决方案：initramfs——一个临时的小型文件系统，内嵌在内核启动过程中。**

```
Bootloader 加载 vmlinuz + initramfs
  → 内核解压 initramfs 到内存中的 tmpfs
  → 内核执行 initramfs 中的 /init 脚本
  → /init 加载必要的驱动模块
  → /init 挂载真正的 rootfs
  → /init 执行 switch_root 切换到真正的 rootfs
  → 真正的 rootfs 上的 /sbin/init 开始执行
```

initramfs 中的 `/init` 通常是一个脚本或小型程序：

```sh
#!/bin/sh
# initramfs /init（简化）
mount -t proc none /proc
mount -t sysfs none /sys

# 加载磁盘驱动
modprobe ahci          # SATA 驱动
modprobe sd_mod        # SCSI 磁盘驱动
modprobe ext4          # 文件系统驱动

# 挂载真正的根文件系统
mount /dev/sda1 /mnt/root

# 切换到真正的根文件系统
exec switch_root /mnt/root /sbin/init
```

**设计哲学：用临时环境解决循环依赖——先建立一个最小环境，用它来建立完整环境，然后丢弃临时环境。**

---

## 四、Trade-offs：启动设计中的关键权衡

### 4.1 压缩 vs 不压缩

| 方案 | 优点 | 缺点 |
|------|------|------|
| 不压缩内核 | 启动快（无需解压） | 磁盘占用大、I/O 时间长 |
| 压缩内核 | 磁盘占用小、I/O 时间短 | 需要 CPU 解压时间 |

**Linux 的选择**：默认压缩（gzip/zstd），因为现代 CPU 解压速度 >> 磁盘读取速度。

### 4.2 内联驱动 vs 模块化驱动

| 方案 | 优点 | 缺点 |
|------|------|------|
| 所有驱动编译进内核 | 不需要 initramfs | 内核镜像巨大、无法动态加载 |
| 驱动作为模块 | 内核镜像小、灵活 | 需要 initramfs 来加载启动所需模块 |

**Linux 的选择**：混合方案——关键驱动（磁盘控制器、根文件系统）可以内联或通过 initramfs 加载，其他驱动作为模块动态加载。

### 4.3 并行初始化 vs 串行初始化

| 方案 | 优点 | 缺点 |
|------|------|------|
| 串行初始化 | 简单、易调试、依赖关系清晰 | 启动慢 |
| 并行初始化 | 启动快 | 依赖关系复杂、难以调试 |

**Linux 的演进**：
- SysV init：严格串行，启动慢
- Upstart：事件驱动，部分并行
- systemd：完全并行 + 依赖图，启动快

systemd 的核心设计：用**依赖图**（dependency graph）描述服务间的关系，然后**拓扑排序**找出可并行启动的服务。

---

## 五、Real-world Analysis：Linux 源码中的关键数据结构

### 5.1 boot_params — 内核与 bootloader 的通信协议

```c
// arch/x86/include/uapi/asm/bootparam.h
struct boot_params {
    struct screen_info screen_info;         // 显示信息
    struct apm_bios_info apm_bios_info;     // APM BIOS 信息
    __u64  tboot_addr;                      // Trusted Boot 地址
    
    struct setup_header hdr;                // 启动头（关键！）
    
    __u8  _pad8[8];
    
    struct e820_entry e820_map[E820MAX];    // 内存映射（关键！）
    __u8  _pad88[48];
    
    struct edd_info eddbuf[EDDMAXNR];       // 磁盘信息
    // ...
};
```

`e820_map` 是最重要的字段——它告诉内核物理内存的布局：

```c
struct e820_entry {
    __u64 addr;    // 内存区域起始地址
    __u64 size;    // 内存区域大小
    __u32 type;    // 类型：1=可用, 2=保留, 3=ACPI, 4=NVS...
} __attribute__((packed));
```

**为什么需要 e820？** 因为物理内存不是连续的——有 BIOS 保留区域、ACPI 区域、内存映射 I/O 区域等。内核必须知道哪些内存可以用，哪些不能用。

### 5.2 init_task — 进程 0 的静态初始化

```c
// init/init_task.c
struct task_struct init_task = {
    .state      = 0,                    // TASK_RUNNING
    .stack      = init_stack,            // 内核栈
    .usage      = REFCOUNT_INIT(2),     // 引用计数
    .flags      = PF_KTHREAD,           // 内核线程标志
    .prio       = MAX_PRIO - 20,        // 优先级
    .static_prio = MAX_PRIO - 20,
    .policy     = SCHED_NORMAL,         // 调度策略
    .mm         = &init_mm,             // 内存描述符
    .active_mm  = &init_mm,
    .pid        = 0,                    // PID 0
    .comm       = "swapper",            // 进程名
    // ...
};
```

**设计哲学：init_task 是静态初始化的——在调度器还没运行之前，就必须有一个"进程"存在。** 它不是通过 `fork()` 创建的，而是编译时就定义好的。

### 5.3 init_mm — 内核地址空间的静态初始化

```c
// mm/init-mm.c
struct mm_struct init_mm = {
    .mm_rb      = RB_ROOT,              // 红黑树根（VMA 管理）
    .mm_mt      = MTREE_INIT,           // Maple tree（新内核）
    .pgd        = swapper_pg_dir,       // 页全局目录
    .mm_users   = ATOMIC_INIT(2),       // 用户计数
    .mm_count   = ATOMIC_INIT(1),       // 总引用计数
    .map_count  = 1,                    // VMA 数量
    // ...
};
```

**关键点：`swapper_pg_dir` 是内核的页全局目录，在编译时就分配好了。** 内核地址空间在启动初期就已经建立，不需要动态分配。

---

## 六、Hands-on Lab：lab01-bootloader

### 实验目标

编写一个最小的 bootloader，理解从"通电"到"执行代码"的完整链条。

### 实验内容

1. **编写 512 字节的 MBR bootloader**（汇编）：
   - 在实模式下运行
   - 打印一条消息到屏幕
   - 读取磁盘上的第二个扇区并跳转执行

2. **编写一个简单的 second-stage loader**（C + ASM）：
   - 切换到保护模式（设置 GDT）
   - 打印一条消息验证保护模式工作

3. **用 QEMU 测试**：
   ```bash
   # 创建启动磁盘镜像
   dd if=/dev/zero of=disk.img bs=512 count=2880
   dd if=boot.bin of=disk.img bs=512 conv=notrunc
   dd if=stage2.bin of=disk.img bs=512 seek=1 conv=notrunc
   
   # 在 QEMU 中启动
   qemu-system-x86_64 -drive format=raw,file=disk.img
   ```

### 关键代码片段

MBR bootloader（NASM 汇编）：

```asm
; boot.asm — 512字节 MBR bootloader
[BITS 16]                    ; 16位实模式
[ORG 0x7C00]                 ; BIOS 加载到 0x7C00

start:
    ; 设置段寄存器
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00           ; 栈指针

    ; 打印消息
    mov si, msg
    call print_string

    ; 加载第二个扇区到 0x7E00
    mov ah, 0x02             ; BIOS 读扇区功能
    mov al, 1                ; 读1个扇区
    mov ch, 0                ; 柱面0
    mov cl, 2                ; 扇区2（从1开始计数）
    mov dh, 0                ; 磁头0
    mov dl, 0x80             ; 第一块硬盘
    mov bx, 0x7E00           ; 加载地址
    int 0x13                 ; BIOS 磁盘中断

    ; 跳转到第二阶段
    jmp 0x7E00

print_string:
    lodsb                    ; 加载 DS:SI 到 AL
    or al, al
    jz .done
    mov ah, 0x0E             ; BIOS teletype 功能
    mov bh, 0
    int 0x10
    jmp print_string
.done:
    ret

msg db 'Stage 1: Hello from MBR!', 0x0D, 0x0A, 0

times 510-($-$$) db 0        ; 填充到510字节
dw 0xAA55                    ; MBR 签名（必须！）
```

**注意最后的 `0xAA55`**——这是 MBR 的魔数签名。BIOS 读取第一个扇区后，会检查最后两个字节是否是 `0xAA55`，如果不是就认为这不是有效的启动扇区。

### 进阶实验

- 修改 bootloader，切换到保护模式并设置 GDT
- 读取内核镜像并加载到内存
- 实现 A20 地址线的启用（为什么需要？因为实模式下第21根地址线被锁定了）

---

## 参考资源

- *Linux Boot Process*: https://0xax.gitbooks.io/linux-insides/content/Booting/
- Linux 源码 `init/main.c` — `start_kernel()` 是整个内核初始化的入口
- Linux 源码 `arch/x86/boot/` — 早期启动代码
- *OSDev Wiki*: https://wiki.osdev.org — 操作系统开发的最佳参考
- *Writing a Simple Operating System — from Scratch* (Nick Blundell) — bootloader 实践入门