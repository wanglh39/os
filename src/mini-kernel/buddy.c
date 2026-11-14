/*
 * Buddy System 分配器实现
 * 模拟 Linux 的伙伴系统：分配、分裂、合并。
 *
 * 编译: gcc buddy.c -o buddy && ./buddy
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_ORDER 10
#define NUM_PAGES 1024

typedef struct page {
    int order;
    int allocated;
    struct page *next;
    struct page *prev;
} page_t;

static page_t pages[NUM_PAGES];
static page_t *free_lists[MAX_ORDER + 1];

static void buddy_init(void) {
    memset(pages, 0, sizeof(pages));
    for (int i = 0; i <= MAX_ORDER; i++)
        free_lists[i] = NULL;

    pages[0].order = MAX_ORDER;
    pages[0].allocated = 0;
    free_lists[MAX_ORDER] = &pages[0];
}

static page_t *buddy_alloc(int order) {
    for (int o = order; o <= MAX_ORDER; o++) {
        if (free_lists[o] != NULL) {
            page_t *block = free_lists[o];
            free_lists[o] = block->next;
            if (block->next) block->next->prev = NULL;

            while (o > order) {
                o--;
                int buddy_idx = (int)(block - pages) + (1 << o);
                page_t *buddy = &pages[buddy_idx];
                buddy->order = o;
                buddy->allocated = 0;
                buddy->next = free_lists[o];
                buddy->prev = NULL;
                if (free_lists[o]) free_lists[o]->prev = buddy;
                free_lists[o] = buddy;
            }

            block->order = order;
            block->allocated = 1;
            return block;
        }
    }
    return NULL;
}

static void buddy_free(page_t *block) {
    int order = block->order;
    block->allocated = 0;

    while (order < MAX_ORDER) {
        int block_idx = (int)(block - pages);
        int buddy_idx = block_idx ^ (1 << order);
        page_t *buddy = &pages[buddy_idx];

        if (buddy->allocated || buddy->order != order)
            break;

        if (buddy->prev) buddy->prev->next = buddy->next;
        else free_lists[order] = buddy->next;
        if (buddy->next) buddy->next->prev = buddy->prev;

        if (buddy_idx < block_idx)
            block = buddy;

        order++;
        block->order = order;
    }

    block->next = free_lists[order];
    block->prev = NULL;
    if (free_lists[order]) free_lists[order]->prev = block;
    free_lists[order] = block;
}

static void print_free_lists(void) {
    for (int o = 0; o <= MAX_ORDER; o++) {
        if (free_lists[o]) {
            printf("  Order %d (%d pages):", o, 1 << o);
            for (page_t *p = free_lists[o]; p; p = p->next)
                printf(" [%ld]", p - pages);
            printf("\n");
        }
    }
}

int main(void) {
    buddy_init();
    printf("=== Initial state ===\n");
    print_free_lists();

    printf("\nAlloc order 2 (4 pages):\n");
    page_t *a = buddy_alloc(2);
    printf("  Block at page %ld\n", a - pages);
    print_free_lists();

    printf("\nAlloc order 3 (8 pages):\n");
    page_t *b = buddy_alloc(3);
    printf("  Block at page %ld\n", b - pages);
    print_free_lists();

    printf("\nFree block a (page %ld):\n", a - pages);
    buddy_free(a);
    print_free_lists();

    printf("\nFree block b (page %ld):\n", b - pages);
    buddy_free(b);
    print_free_lists();

    printf("\nAlloc order 10 (all pages):\n");
    page_t *c = buddy_alloc(10);
    printf("  Block at page %ld, %s\n", c - pages, c ? "success" : "failed");

    return 0;
}