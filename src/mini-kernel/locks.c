/*
 * 自旋锁与 CAS 原子操作演示
 * 对比自旋锁和 CAS 两种并发控制方式。
 *
 * 编译: gcc locks.c -o locks -lpthread && ./locks
 */
#include <stdio.h>
#include <pthread.h>
#include <stdatomic.h>

typedef struct {
    atomic_flag locked;
} spinlock_t;

static void spin_lock(spinlock_t *lock) {
    while (atomic_flag_test_and_set_explicit(&lock->locked,
                                              memory_order_acquire)) {
    }
}

static void spin_unlock(spinlock_t *lock) {
    atomic_flag_clear_explicit(&lock->locked, memory_order_release);
}

typedef struct {
    int value;
} atomic_counter_t;

static void counter_add(atomic_counter_t *c, int val) {
    int old, new_val;
    do {
        old = c->value;
        new_val = old + val;
    } while (!__sync_bool_compare_and_swap(&c->value, old, new_val));
}

static spinlock_t lock = {0};
static atomic_counter_t counter = {0};

static void *spinlock_worker(void *arg) {
    (void)arg;
    for (int i = 0; i < 100000; i++) {
        spin_lock(&lock);
        counter.value++;
        spin_unlock(&lock);
    }
    return NULL;
}

static void *cas_worker(void *arg) {
    (void)arg;
    for (int i = 0; i < 100000; i++) {
        counter_add(&counter, 1);
    }
    return NULL;
}

int main(void) {
    pthread_t threads[4];

    printf("=== Spinlock test ===\n");
    counter.value = 0;
    for (int i = 0; i < 4; i++)
        pthread_create(&threads[i], NULL, spinlock_worker, NULL);
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