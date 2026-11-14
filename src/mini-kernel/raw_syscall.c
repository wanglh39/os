/*
 * 直接系统调用演示
 * 绕过 glibc，直接使用 syscall 指令发起系统调用。
 *
 * 编译: gcc raw_syscall.c -o raw_syscall && ./raw_syscall
 */
#include <unistd.h>
#include <sys/syscall.h>
#include <stdio.h>

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

int main(void) {
    const char *msg = "Hello, raw syscall!\n";
    long ret = my_syscall(SYS_write, 1, (long)msg, 19);
    printf("write returned: %ld\n", ret);

    long pid = my_syscall(SYS_getpid, 0, 0, 0);
    printf("getpid returned: %ld\n", pid);

    return 0;
}