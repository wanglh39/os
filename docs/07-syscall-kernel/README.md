# 07 - 系统调用与内核接口

> "The system call interface is the contract between user space and kernel space."

---

## 一、Design Philosophy：系统调用在解决什么问题？

### 1.1 核心问题

如果用户程序可以直接访问硬件和内核数据：

```c
// 假设没有系统调用的世界
void malicious_program() {
    // 直接读写内核内存
    int *kernel_data = (int *)0xFFFFFFFF_80000000;
    *kernel_data = 0;  // 破坏内核数据！

    // 直接操作磁盘
    outb(0x1F7, 0x20);  // 绕过文件系统直接读磁盘

    // 直接修改页表
    write_cr3(my_evil_page_table);
}
```

**没有隔离的世界：任何 bug 或恶意代码都能搞垮整个系统。**

系统调用解决的核心问题：**如何让用户程序安全地使用内核功能？**

### 1.2 User/Kernel Mode 隔离

硬件提供两个（或更多）特权级：

| 特权级 | 名称 | 能做什么 | 谁运行在这里 |
|--------|------|---------|-------------|
| Ring 0 | Kernel Mode | 任何指令、任何内存 | 内核 |
| Ring 3 | User Mode | 受限指令、只能访问自己的内存 | 用户程序 |

**关键硬件机制**：
1. **特权指令**：`cli`（关中断）、`hlt`（停机）、`wrmsr`（写 MSR）、`mov cr3`（切换页表）——只能在 Ring 0 执行
2. **内存隔离**：页表条目的 U/S 位——Ring 3 不能访问标记为 Supervisor 的页
3. **I/O 隔离**：I/O 权限位图——Ring 3 不能直接执行 `in`/`out` 指令（除非特别授权）

**系统调用是 User Mode 进入 Kernel Mode 的唯一合法通道。**

### 1.3 系统调用 vs 函数调用

普通函数调用和系统调用有本质区别：

```
普通函数调用：
  push 参数 → push 返回地址 → jmp 函数 → 函数执行 → ret
  同一个特权级，同一个地址空间

系统调用：
  1. 用户态准备参数
  2. 执行特殊指令（syscall/int 0x80）
  3. CPU 切换到 Ring 0
  4. 切换到内核栈
  5. 内核执行系统调用处理函数
  6. 返回用户态（sysret/iret）
  7. CPU 切换回 Ring 3
  8. 切换回用户栈
```

**系统调用的开销远大于函数调用**——特权级切换、栈切换、TLB 可能部分刷新。现代 CPU 上约 100-200 cycles，而函数调用约 2-5 cycles。

---

## 二、Historical Evolution：系统调用的演进

### 2.1 int 0x80（Linux 早期）

```asm
; 早期 Linux 系统调用（int 0x80）
mov eax, 1          ; sys_write 的编号
mov ebx, 1          ; fd = stdout
mov ecx, msg        ; buffer
mov edx, 13         ; length
int 0x80            ; 触发软中断
```

`int 0x80` 的问题：
- 中断指令开销大（查 IDT、权限检查、上下文保存）
- 所有参数通过寄存器传递（限制参数数量）
- 每次系统调用约 200-400 cycles

### 2.2 sysenter/sysexit（Pentium II+）

Intel 引入的快速系统调用指令：

```asm
sysenter            ; 快速进入内核
; CPU 自动：
;   1. 从 MSR 加载 CS, SS, ESP, EIP
;   2. 切换到 Ring 0
;   3. 跳转到内核入口

sysexit             ; 快速返回用户态
```

比 `int 0x80` 快，但 AMD 和 Intel 的实现不兼容。

### 2.3 syscall/sysret（x86-64，现代标准）

AMD 设计，现在 x86-64 的标准方式：

```asm
syscall             ; 最快的系统调用方式
; CPU 自动：
;   1. 保存 RIP 到 RCX
;   2. 保存 RFLAGS 到 R11
;   3. 从 MSR 加载 CS, SS
;   4. 切换到 Ring 0
;   5. 跳转到 MSR_LSTAR 指定的入口

sysret              ; 快速返回
; CPU 自动：
;   1. 从 RCX 恢复 RIP
;   2. 从 R11 恢复 RFLAGS
;   3. 切换回 Ring 3
```

`syscall` 的优势：
- 不查 IDT（直接从 MSR 加载目标地址）
- 不保存完整的上下文（只保存必要的 RIP 和 RFLAGS）
- 约 100-150 cycles

### 2.4 vDSO — 虚拟动态共享对象

有些"系统调用"其实不需要进入内核——比如 `gettimeofday()` 只是读取内核维护的时间变量。

vDSO 的解决方案：**把一小段内核代码映射到用户进程的地址空间，用户进程直接调用，不需要特权级切换。**

```
gettimeofday() 的两种路径：

1. vDSO 路径（快）：
   用户调用 gettimeofday → 跳转到 vDSO 中的代码
   → 读取内核维护的时间变量（映射到用户空间）
   → 返回 → 0 cycles 特权级切换

2. 系统调用路径（慢）：
   用户调用 gettimeofday → syscall → 内核处理 → sysret
   → 100+ cycles 特权级切换
```

**设计哲学：能不进内核就不进内核——把只读的内核数据映射到用户空间，避免不必要的特权级切换。**

---

## 三、Core Mechanism：系统调用的完整流程

### 3.1 系统调用编号

每个系统调用有一个唯一编号。x86-64 Linux 约有 350+ 个系统调用：

```c
// include/uapi/asm-generic/unistd.h（部分）
#define __NR_read       0
#define __NR_write      1
#define __NR_open       2
#define __NR_close      3
#define __NR_stat       4
#define __NR_fstat      5
#define __NR_lstat      6
#define __NR_poll       7
#define __NR_lseek      8
#define __NR_mmap       9
#define __NR_mprotect   10
#define __NR_munmap     11
#define __NR_brk        12
// ...
#define __NR_clone      220
#define __NR_execve     221
#define __NR_exit       231
#define __NR_epoll_wait 281
#define __NR_io_uring_setup 425
#define __NR_io_uring_enter 426
```

### 3.2 参数传递

x86-64 Linux 的系统调用参数传递约定：

| 寄存器 | 用途 |
|--------|------|
| RAX | 系统调用编号（输入）/ 返回值（输出） |
| RDI | 第1个参数 |
| RSI | 第2个参数 |
| RDX | 第3个参数 |
| R10 | 第4个参数（注意：不是 RCX，因为 syscall 用 RCX 保存 RIP） |
| R8 | 第5个参数 |
| R9 | 第6个参数 |

最多 6 个参数。如果需要更多，通过结构体传递（指针指向用户空间的参数结构）。

### 3.3 完整调用链

```
用户程序调用 write(fd, buf, count)
  │
  ↓
glibc 的 write() 包装函数
  │  mov $1, %rax        ; __NR_write
  │  mov %rdi, %rdi      ; fd
  │  mov %rsi, %rsi      ; buf
  │  mov %rdx, %rdx      ; count
  │  syscall
  ↓
CPU 执行 syscall 指令
  │  1. 保存 RIP → RCX
  │  2. 保存 RFLAGS → R11
  │  3. 从 MSR_STAR 加载 CS=0x10 (kernel CS), SS=0x18 (kernel SS)
  │  4. 从 MSR_LSTAR 加载 RIP=entry_SYSCALL_64
  │  5. 切换到 Ring 0
  ↓
entry_SYSCALL_64（arch/x86/entry/entry_64.S）
  │  1. 切换到内核栈（从 TSS 读取 RSP）
  │  2. 保存用户态寄存器到内核栈（pt_regs 结构）
  │  3. 调用 do_syscall_64()
  ↓
do_syscall_64（arch/x86/entry/common.c）
  │  1. 从 RAX 读取系统调用编号
  │  2. 从 RDI/RSI/RDX/R10/R8/R9 读取参数
  │  3. 查 sys_call_table[rax]
  │  4. 调用 sys_write(fd, buf, count)
  ↓
sys_write（fs/read_write.c）
  │  1. 检查 fd 是否有效
  │  2. 检查 buf 是否可读（用户空间地址验证）
  │  3. 调用 vfs_write()
  │  4. 返回写入的字节数
  ↓
返回路径
  │  1. 返回值放入 RAX
  │  2. 恢复用户态寄存器
  │  3. sysret 指令返回 Ring 3
```

### 3.4 系统调用表

```c
// arch/x86/entry/syscalls/syscall_64.tbl（部分）
0   common  read        sys_read
1   common  write       sys_write
2   common  open        sys_open
3   common  close       sys_close
// ...

// 生成的代码（简化）
const sys_call_ptr_t sys_call_table[] = {
    [0] = sys_read,
    [1] = sys_write,
    [2] = sys_open,
    [3] = sys_close,
    // ...
};
```

### 3.5 安全检查

内核必须验证用户传入的所有参数：

```c
// 用户空间地址验证
static inline bool access_ok(const void __user *addr, unsigned long size)
{
    // 检查地址是否在用户空间范围内
    return (unsigned long)addr < TASK_SIZE_MAX;
}

// 安全地从用户空间读取
copy_from_user(kernel_buf, user_buf, size);
// 安全地写入用户空间
copy_to_user(user_buf, kernel_buf, size);
```

**为什么不能直接 `memcpy`？**
1. 用户传入的地址可能无效（触发缺页异常）
2. 用户传入的地址可能在内核空间（安全漏洞！）
3. 用户传入的地址可能被其他线程修改（TOCTOU 攻击）

`copy_from_user`/`copy_to_user` 会：
1. 先用 `access_ok` 检查地址范围
2. 在异常处理框架下拷贝（如果缺页，不会 panic 而是返回错误）

---

## 四、Trade-offs：系统调用设计的关键权衡

### 4.1 粒度：粗粒度 vs 细粒度

| 方案 | 优点 | 缺点 | 代表 |
|------|------|------|------|
| 粗粒度（少而强大） | 灵活、可组合 | 学习成本高、容易误用 | Unix/Linux |
| 细粒度（多而简单） | 易学、安全 | 不灵活、系统调用爆炸 | Windows |

**Unix 的设计哲学**：提供少量强大的系统调用（如 `open`、`read`、`write`、`mmap`），通过组合实现复杂功能。

**Windows 的设计哲学**：提供大量专门的 API（如 `CreateFile`、`ReadFile`、`WriteFile`），每个 API 做一件事。

### 4.2 同步 vs 异步系统调用

| 方案 | 优点 | 缺点 |
|------|------|------|
| 同步（阻塞） | 简单、易理解 | 线程阻塞、需要多线程 |
| 异步（非阻塞） | 高并发、不阻塞 | 编程复杂 |

**Linux 的选择**：大部分系统调用是同步的，但提供异步选项：
- `O_NONBLOCK`：非阻塞 I/O
- `io_uring`：真正的异步 I/O
- `aio_read`/`aio_write`：POSIX 异步 I/O（实现不佳）

### 4.3 系统调用 vs 内核模块

| 方案 | 优点 | 缺点 |
|------|------|------|
| 增加系统调用 | 直接、高效 | 需要修改内核、不可移植 |
| 内核模块 | 动态加载、不修改内核 | 安全风险、API 不稳定 |
| 用户态实现 | 安全、可移植 | 性能差、功能受限 |

**Linux 的选择**：系统调用数量保持稳定，新功能尽量通过内核模块或用户态实现。`io_uring` 是近年来少有的新增系统调用。

---

## 五、Real-world Analysis：Linux 系统调用源码

### 5.1 entry_SYSCALL_64 — 系统调用入口

```asm
// arch/x86/entry/entry_64.S（简化）
SYM_INNER_LABEL(entry_SYSCALL_64, SYM_L_GLOBAL)
    # 1. 交换 GS（切换到内核 GS）
    swapgs

    # 2. 保存用户态栈指针
    movq    %rsp, PER_CPU_OFFSET(cpu_tss_rw + TSS_sp2)
    
    # 3. 切换到内核栈
    movq    PER_CPU_OFFSET(cpu_tss_rw + TSS_sp1), %rsp

    # 4. 保存用户态寄存器（构建 pt_regs）
    pushq   $__USER_DS            # SS
    pushq   PER_CPU_OFFSET(cpu_tss_rw + TSS_sp2)  # RSP（用户栈）
    pushq   %r11                  # RFLAGS（被 syscall 保存）
    pushq   $__USER_CS            # CS
    pushq   %rcx                  # RIP（被 syscall 保存）
    
    # 保存其他寄存器
    pushq   %rdi; pushq %rsi; pushq %rdx
    pushq   %r10; pushq %r8; pushq %r9
    
    # 5. 调用 C 函数
    movq    %rsp, %rdi             # pt_regs 作为参数
    call    do_syscall_64

    # 6. 返回用户态
    movq    %rax, RAX(%rsp)        # 保存返回值
    
    # 恢复寄存器
    popq    %r9; popq %r8; popq %r10
    popq    %rdx; popq %rsi; popq %rdi
    
    popq    %rcx                  # 恢复 RIP
    # ... 恢复 CS, RFLAGS, RSP, SS
    
    swapgs                          # 切换回用户 GS
    sysretq                         # 返回 Ring 3
```

### 5.2 do_syscall_64 — 系统调用分发

```c
// arch/x86/entry/common.c（简化）
__visible noinstr void do_syscall_64(struct pt_regs *regs, int nr)
{
    // 从寄存器读取参数
    unsigned long args[6] = {
        regs->di, regs->si, regs->dx,
        regs->r10, regs->r8, regs->r9
    };
    
    // 查系统调用表并调用
    if (likely(nr < NR_syscalls)) {
        nr = array_index_nospec(nr, NR_syscalls);  // 防止 Spectre
        regs->ax = sys_call_table[nr](args[0], args[1], args[2],
                                       args[3], args[4], args[5]);
    } else {
        regs->ax = -ENOSYS;  // 未知系统调用
    }
}
```

**注意 `array_index_nospec`**——这是 Spectre 漏洞的缓解措施，防止用户通过系统调用编号进行侧信道攻击。

### 5.3 pt_regs — 上下文保存结构

```c
// arch/x86/include/asm/ptrace.h
struct pt_regs {
    unsigned long r15, r14, r13, r12;
    unsigned long bp, bx;
    unsigned long r11, r10, r9, r8;
    unsigned long ax, cx, dx, si, di;
    unsigned long orig_ax;    // 原始系统调用编号
    unsigned long ip, cs, flags, sp, ss;
};
```

**pt_regs 是系统调用上下文的核心**——它保存了用户态的所有寄存器状态，使得内核可以安全地修改寄存器后返回用户态。

---

## 六、Hands-on Lab：lab06-syscall

### 实验1：用 C 直接发起系统调用（绕过 glibc）

```c
// src/mini-kernel/raw_syscall.c
#include <unistd.h>
#include <sys/syscall.h>
#include <stdio.h>

// 直接使用 syscall 指令，绕过 glibc
static inline long my_syscall(long nr, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile (
        "syscall"
        : "=a"(ret)
        : "a"(nr), "D"(a1), "S"(a2), "d"(a3)
        : "rcx", "r11", "memory"
    );
    return ret;
}

int main() {
    // 直接调用 sys_write(1, msg, 12)
    const char *msg = "Hello, raw syscall!\n";
    long ret = my_syscall(SYS_write, 1, (long)msg, 19);
    printf("write returned: %ld\n", ret);
    
    // 直接调用 sys_getpid
    long pid = my_syscall(SYS_getpid, 0, 0, 0);
    printf("getpid returned: %ld\n", pid);
    
    return 0;
}
```

编译运行：
```bash
gcc raw_syscall.c -o raw_syscall && ./raw_syscall
```

### 实验2：Python 模拟系统调用分发

```python
# src/simulators/syscall_sim.py
from dataclasses import dataclass
from typing import Dict, Callable, Any

@dataclass
class ProcessState:
    pid: int
    user_stack: int
    kernel_stack: int
    registers: Dict[str, int]
    in_kernel: bool = False

class Kernel:
    def __init__(self):
        self.syscall_table: Dict[int, Callable] = {}
        self.current_process: ProcessState = None
        self._register_syscalls()
    
    def _register_syscalls(self):
        self.syscall_table[0] = self.sys_read
        self.syscall_table[1] = self.sys_write
        self.syscall_table[2] = self.sys_open
        self.syscall_table[3] = self.sys_close
        self.syscall_table[9] = self.sys_mmap
        self.syscall_table[39] = self.sys_getpid
        self.syscall_table[60] = self.sys_exit
    
    def syscall(self, nr, args):
        """模拟系统调用入口"""
        print(f"  [SYSCALL] nr={nr}, args={args}")
        
        # 1. 切换到内核态
        self.current_process.in_kernel = True
        self.current_process.registers['rax'] = nr
        
        # 2. 安全检查
        if nr not in self.syscall_table:
            print(f"  [ERROR] Unknown syscall {nr}")
            self.current_process.registers['rax'] = -38  # -ENOSYS
            self.current_process.in_kernel = False
            return
        
        # 3. 调用系统调用处理函数
        handler = self.syscall_table[nr]
        ret = handler(*args)
        
        # 4. 设置返回值
        self.current_process.registers['rax'] = ret
        
        # 5. 切换回用户态
        self.current_process.in_kernel = False
        print(f"  [RETURN] ret={ret}")
        return ret
    
    # 系统调用实现
    def sys_read(self, fd, buf, count):
        print(f"    read(fd={fd}, buf={buf}, count={count})")
        return count  # 简化：总是成功
    
    def sys_write(self, fd, buf, count):
        print(f"    write(fd={fd}, buf={buf}, count={count})")
        return count
    
    def sys_open(self, path, flags, mode):
        print(f"    open(path={path}, flags={flags}, mode={mode})")
        return 3  # 简化：返回 fd=3
    
    def sys_close(self, fd):
        print(f"    close(fd={fd})")
        return 0
    
    def sys_mmap(self, addr, length, prot, flags, fd, offset):
        print(f"    mmap(addr={addr}, length={length}, ...)")
        return 0x7F0000000000  # 简化：返回虚拟地址
    
    def sys_getpid(self):
        print(f"    getpid()")
        return self.current_process.pid
    
    def sys_exit(self, code):
        print(f"    exit(code={code})")
        return 0

if __name__ == "__main__":
    kernel = Kernel()
    proc = ProcessState(pid=1234, user_stack=0x7FFF0000, kernel_stack=0xFFFF8000,
                        registers={'rax': 0, 'rdi': 0, 'rsi': 0, 'rdx': 0})
    kernel.current_process = proc
    
    print("=== Simulating syscalls ===\n")
    
    # write(1, "hello", 5)
    kernel.syscall(1, [1, 0x400000, 5])
    
    # getpid()
    kernel.syscall(39, [])
    
    # open("/etc/passwd", O_RDONLY, 0)
    kernel.syscall(2, [0x500000, 0, 0])
    
    # read(3, buf, 4096)
    kernel.syscall(0, [3, 0x600000, 4096])
    
    # close(3)
    kernel.syscall(3, [3])
    
    # exit(0)
    kernel.syscall(60, [0])
```

### 进阶实验

- 用 `strace` 工具观察真实程序的系统调用序列
- 实现一个简单的内核模块添加自定义系统调用
- 模拟 vDSO 机制：把"内核数据"映射到"用户空间"

---

## 参考资源

- Linux 源码 `arch/x86/entry/` — 系统调用入口
- Linux 源码 `arch/x86/entry/syscalls/syscall_64.tbl` — 系统调用表
- *Understanding the Linux Kernel* Ch.10 — 系统调用
- *Linux Kernel Development* Ch.5 — 系统调用
- strace 工具：跟踪程序的系统调用
- vDSO 文档：https://man7.org/linux/man-pages/man7/vdso.7.html