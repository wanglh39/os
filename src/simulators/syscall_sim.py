"""
系统调用分发模拟器
模拟 user/kernel mode 切换、系统调用表查找、参数传递和安全检查。
"""
from dataclasses import dataclass
from typing import Dict, Callable


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
        print(f"  [SYSCALL] nr={nr}, args={args}")

        self.current_process.in_kernel = True
        self.current_process.registers['rax'] = nr

        if nr not in self.syscall_table:
            print(f"  [ERROR] Unknown syscall {nr}")
            self.current_process.registers['rax'] = -38
            self.current_process.in_kernel = False
            return -38

        handler = self.syscall_table[nr]
        ret = handler(*args)

        self.current_process.registers['rax'] = ret
        self.current_process.in_kernel = False
        print(f"  [RETURN] ret={ret}")
        return ret

    def sys_read(self, fd, buf, count):
        print(f"    read(fd={fd}, buf=0x{buf:X}, count={count})")
        return count

    def sys_write(self, fd, buf, count):
        print(f"    write(fd={fd}, buf=0x{buf:X}, count={count})")
        return count

    def sys_open(self, path, flags, mode):
        print(f"    open(path=0x{path:X}, flags={flags}, mode={mode})")
        return 3

    def sys_close(self, fd):
        print(f"    close(fd={fd})")
        return 0

    def sys_mmap(self, addr, length, prot, flags, fd, offset):
        print(f"    mmap(addr=0x{addr:X}, length={length}, ...)")
        return 0x7F0000000000

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

    kernel.syscall(1, [1, 0x400000, 5])
    kernel.syscall(39, [])
    kernel.syscall(2, [0x500000, 0, 0])
    kernel.syscall(0, [3, 0x600000, 4096])
    kernel.syscall(3, [3])
    kernel.syscall(60, [0])