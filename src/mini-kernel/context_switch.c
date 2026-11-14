/*
 * 上下文切换演示
 * 使用 ucontext 在两个"进程"之间切换，模拟调度器行为。
 *
 * 编译: gcc context_switch.c -o context_switch && ./context_switch
 */
#include <stdio.h>
#include <ucontext.h>
#include <stdlib.h>

#define STACK_SIZE 16384

static ucontext_t main_ctx, ctx_a, ctx_b;

static void func_a(void) {
    for (int i = 0; i < 3; i++) {
        printf("Process A: step %d\n", i);
        swapcontext(&ctx_a, &ctx_b);
    }
    printf("Process A: done\n");
    swapcontext(&ctx_a, &main_ctx);
}

static void func_b(void) {
    for (int i = 0; i < 3; i++) {
        printf("Process B: step %d\n", i);
        swapcontext(&ctx_b, &ctx_a);
    }
    printf("Process B: done\n");
    swapcontext(&ctx_b, &main_ctx);
}

int main(void) {
    char stack_a[STACK_SIZE];
    char stack_b[STACK_SIZE];

    getcontext(&ctx_a);
    ctx_a.uc_stack.ss_sp = stack_a;
    ctx_a.uc_stack.ss_size = STACK_SIZE;
    ctx_a.uc_link = &main_ctx;
    makecontext(&ctx_a, func_a, 0);

    getcontext(&ctx_b);
    ctx_b.uc_stack.ss_sp = stack_b;
    ctx_b.uc_stack.ss_size = STACK_SIZE;
    ctx_b.uc_link = &main_ctx;
    makecontext(&ctx_b, func_b, 0);

    printf("=== Start scheduling ===\n");
    swapcontext(&main_ctx, &ctx_a);
    printf("=== All processes done ===\n");

    return 0;
}