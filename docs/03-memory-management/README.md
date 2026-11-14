# 03 - 内存管理

> "Memory is the core resource that the OS manages. Everything else is built on top of it."

---

## 一、Design Philosophy：内存管理在解决什么问题？

### 1.1 核心问题

物理内存是**有限**且**共享**的资源。OS 需要解决：

1. **分配**：如何高效地把内存分给需要的进程？
2. **回收**：如何高效地回收不再使用的内存？
3. **碎片**：如何避免内存碎片导致无法分配大块连续内存？
4. **隔离**：如何防止进程之间互相干扰？

### 1.2 分配器的层次结构

Linux 内存管理是**分层**的，每层解决不同的问题：

```
┌──────────────────────────────────────────────┐
│  用户态分配器 (malloc / new)                  │ ← 应用看到的接口
│  - ptmalloc, jemalloc, tcmalloc              │
├──────────────────────────────────────────────┤
│  内核分配器                                    │ ← 内核代码使用的接口
│  - slab/slub/slob: 小对象分配                 │
│  - vmalloc: 虚拟连续、物理不连续              │
├──────────────────────────────────────────────┤
│  页面分配器 (Buddy System)                    │ ← 物理页管理
│  - 以页（4KB）为单位分配                      │
├──────────────────────────────────────────────┤
│  Zone 管理                                    │ ← 物理内存分区
│  - DMA / DMA32 / NORMAL / HIGH               │
├──────────────────────────────────────────────┤
│  物理内存 (RAM)                               │
└──────────────────────────────────────────────┘
```

**设计哲学：分层分配——每层处理特定粒度的分配需求，避免用一个机制解决所有问题。**

---

## 二、Historical Evolution：内存分配的演进

### 2.1 早期方案：固定分区

把内存分成固定大小的分区，每个分区放一个进程。

```
┌──────────┬──────────┬──────────┬──────────┐
│ Partition│ Partition│ Partition│ Partition│
│   0      │   1      │   2      │   3      │
│ 64KB     │ 64KB     │ 64KB     │ 64KB     │
└──────────┴──────────┴──────────┴──────────┘
```

问题：内部碎片（进程用不满分区）+ 外部碎片（分区大小固定，不灵活）。

### 2.2 可变分区

根据进程需求分配恰好大小的内存。

```
┌──────┬──────┬──────┬────────────┐
│ ProcA│ ProcB│ ProcC│ Free       │
│ 20KB │ 50KB │ 30KB │ 100KB      │
└──────┴──────┴──────┴────────────┘
```

问题：随着进程创建和销毁，内存中出现越来越多的小空洞——**外部碎片**。

```
创建 → 销毁 → 创建 → 销毁 → ...

┌────┬────┬──┬────┬──┬────┬──┬────┬────────┐
│ A  │ B  │  │ C  │  │ D  │  │ E  │ Free   │
│20KB│50KB│8K│30KB│8K│40KB│8K│20KB│ 60KB   │
└────┴────┴──┴────┴──┴────┴──┴────┴────────┘
         ↑    ↑    ↑    ↑
         碎片  碎片  碎片  碎片

总空闲 = 60 + 8*3 = 84KB，但最大连续空闲 = 60KB
```

### 2.3 分页（Paging）

**分页是内存管理的革命性突破**——消除外部碎片。

把内存分成固定大小的**页框**（page frame，通常 4KB），把进程的虚拟地址空间分成同样大小的**页**（page）。

```
虚拟页 → 映射到 → 物理页框（不需要连续！）

进程A的虚拟空间:        物理内存:
┌──────────┐           ┌──────────┐
│ Page 0   │ ────────→ │ Frame 3  │
│ Page 1   │ ────────→ │ Frame 7  │
│ Page 2   │ ────────→ │ Frame 1  │
│ Page 3   │ ────────→ │ Frame 9  │
└──────────┘           └──────────┘
```

**分页消除了外部碎片**——因为每个页框大小相同，任何空闲页框都可以满足任何页的分配需求。

但**内部碎片仍然存在**——如果一个进程需要 5KB，必须分配 2 页（8KB），浪费 3KB。

### 2.4 Buddy System

分页解决了外部碎片，但**大块分配**仍然有问题——需要分配 1MB 连续物理内存时，需要找 256 个连续的空闲页框。

Buddy System 的解决方案：**按 2 的幂次方大小分组管理空闲页。**

```
空闲链表（每个链表只含特定大小的块）:

Order 0 (4KB):  [Frame 5] [Frame 8] [Frame 12]
Order 1 (8KB):  [Frame 20-21]
Order 2 (16KB): [Frame 40-43]
Order 3 (32KB): 
Order 4 (64KB): [Frame 128-135]
...
Order 10 (4MB): 
```

分配 12KB → 分配 Order 2 (16KB)，浪费 4KB（内部碎片）。
分配 8KB → 分配 Order 1 (8KB)，恰好。

当 Order 1 没有空闲块时，从 Order 2 分裂：
```
Order 2: [Frame 40-43]  →  分裂成两个 Order 1 块
Order 1: [Frame 40-41] [Frame 42-43]
分配 [Frame 40-41]，[Frame 42-43] 留在 Order 1 空闲链表
```

释放时，如果"伙伴"（buddy）也空闲，就合并：
```
释放 Frame 40-41 → 检查伙伴 Frame 42-43 是否空闲
  → 如果空闲，合并成 Order 2 块 [Frame 40-43]
  → 继续检查 Order 2 的伙伴是否空闲...
```

**Buddy System 的设计哲学：用 2 的幂次方大小简化合并判断——每个块只有一个伙伴，检查合并只需 O(1)。**

### 2.5 Slab Allocator

Buddy System 的最小粒度是 1 页（4KB），但内核经常需要分配小对象（如 inode、task_struct、file 结构）。

如果用 Buddy System 分配 1 页给一个 200 字节的对象，浪费 3896 字节——严重的内部碎片。

Slab Allocator 的解决方案：**从 Buddy System 拿到页后，把页切成固定大小的小对象。**

```
一个 4KB 页（Slab）被切成 20 个 200 字节的对象：

┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐
│obj0│obj1│obj2│obj3│obj4│obj5│obj6│obj7│obj8│obj9│ ... (共20个)
└────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘

每个对象 200 字节，20 × 200 = 4000 字节，剩余 96 字节用于 slab 管理元数据
```

Slab 的三个核心概念：

1. **Cache**：一种特定类型对象的池（如 `inode_cache`、`task_struct_cache`）
2. **Slab**：cache 中的一个页或一组页，包含多个对象
3. **Object**：slab 中的一个具体对象

```c
// 简化的 slab cache 结构
struct kmem_cache {
    char *name;                 // cache 名称（如 "inode_cache"）
    size_t object_size;         // 每个对象的大小
    size_t align;               // 对齐要求
    unsigned int slab_size;     // 每个 slab 占用的页数
    
    struct list_head slabs_partial;  // 部分使用的 slab
    struct list_head slabs_full;     // 完全使用的 slab
    struct list_head slabs_free;     // 完全空闲的 slab
    
    // 统计信息
    unsigned long active_objects;
    unsigned long num_objects;
    // ...
};
```

**Slab 的设计哲学：针对频繁分配/释放的同类型对象做专门优化——预分配、缓存友好、零初始化。**

Linux 的 slab 实现经历了三代：
- **SLAB**：原始实现，复杂但功能完整
- **SLUB**：简化版，默认选择，性能更好
- **SLOB**：极简版，用于嵌入式系统

---

## 三、Core Mechanism：Buddy System 的详细实现

### 3.1 Zone 和 Node

物理内存不是均匀的——DMA 区域有特殊限制，NUMA 架构中不同节点访问速度不同。

```c
// include/linux/mmzone.h
struct zone {
    unsigned long _watermark[NR_WMARK];  // 水位线（min/low/high）
    unsigned long managed_pages;          // 管理的页数
    
    struct free_area free_area[MAX_ORDER]; // Buddy System 空闲区域
    
    struct per_cpu_pageset *pageset;      // per-CPU 页缓存
    
    // 统计
    atomic_long_t vm_stat[NR_VM_ZONE_STAT_ITEMS];
};

typedef struct pglist_data {
    struct zone node_zones[MAX_NR_ZONES];  // Zone 数组
    // ...
} pg_data_t;
```

Zone 类型：

| Zone | 用途 | 为什么需要 |
|------|------|-----------|
| ZONE_DMA | 旧式 ISA DMA 设备只能寻址 16MB 以下 | 硬件限制 |
| ZONE_DMA32 | 32位设备只能寻址 4GB 以下 | 硬件限制 |
| ZONE_NORMAL | 正常使用的内存 | 默认分配区域 |
| ZONE_HIGHMEM | 32位系统中超出内核直接映射范围的内存 | 32位内核地址空间限制（64位系统不需要） |

### 3.2 free_area — Buddy System 的核心数据结构

```c
struct free_area {
    struct list_head free_list[MIGRATE_TYPES];  // 每种迁移类型一个链表
    unsigned long nr_free;                       // 空闲块数量
};
```

迁移类型（MIGRATE_TYPES）：

| 类型 | 含义 | 为什么需要 |
|------|------|-----------|
| MIGRATE_UNMOVABLE | 不可移动（内核代码、DMA buffer） | 不能被迁移 |
| MIGRATE_MOVABLE | 可移动（用户进程页） | 可以迁移以减少碎片 |
| MIGRATE_RECLAIMABLE | 可回收（文件缓存页） | 可以丢弃后重新加载 |
| MIGRATE_CMA | 连续内存分配器专用 | 给大块连续分配预留 |

**迁移类型的设计哲学：把不同类型的页分开管理，减少碎片——可移动的页可以迁移来腾出连续空间。**

### 3.3 分配流程

```c
// mm/page_alloc.c（简化）
struct page *alloc_pages(unsigned int order, gfp_t gfp_mask)
{
    return __alloc_pages_nodemask(gfp_mask, order, ...);
}

static struct page *__alloc_pages_nodemask(gfp_t gfp_mask, unsigned int order, ...)
{
    // 1. 从指定 zone 的 free_area[order] 中查找
    struct page *page = __rmqueue(preferred_zone, order, ...);
    
    if (page)
        return page;
    
    // 2. 如果没有，从更高 order 分裂
    page = __rmqueue_fallback(preferred_zone, order, ...);
    
    if (page)
        return page;
    
    // 3. 如果还是没有，唤醒 kswapd 回收内存
    // 或者直接回收（__alloc_pages_direct_reclaim）
    
    // 4. OOM killer
    return NULL;
}
```

分裂过程：

```c
// 简化的 __rmqueue
static struct page *__rmqueue(struct zone *zone, unsigned int order)
{
    // 从 order 开始向上查找空闲块
    for (int current_order = order; current_order < MAX_ORDER; current_order++) {
        struct free_area *area = &zone->free_area[current_order];
        
        if (list_empty(&area->free_list[MIGRATE_MOVABLE]))
            continue;
        
        // 找到了！
        struct page *page = list_first_entry(&area->free_list[MIGRATE_MOVABLE],
                                              struct page, lru);
        list_del(&page->lru);
        area->nr_free--;
        
        // 如果 current_order > order，需要分裂
        if (current_order > order) {
            // 从 current_order 逐级分裂到 order
            int size = 1 << current_order;
            while (current_order > order) {
                current_order--;
                size >>= 1;
                // 把后半部分放回低 order 的空闲链表
                struct page *buddy = page + size;
                list_add(&buddy->lru, &zone->free_area[current_order].free_list[...]);
                zone->free_area[current_order].nr_free++;
            }
        }
        
        return page;
    }
    return NULL;
}
```

### 3.4 释放流程

```c
// mm/page_alloc.c（简化）
void free_pages(struct page *page, unsigned int order)
{
    __free_pages(page, order);
}

static void __free_pages(struct page *page, unsigned int order)
{
    // 从 order 开始尝试合并
    while (order < MAX_ORDER - 1) {
        // 计算伙伴块的索引
        unsigned long buddy_idx = page_to_pfn(page) ^ (1 << order);
        struct page *buddy = page + (buddy_idx - page_to_pfn(page));
        
        // 检查伙伴是否也空闲
        if (!PageBuddy(buddy) || page_order(buddy) != order)
            break;  // 伙伴不空闲，停止合并
        
        // 伙伴也空闲，合并！
        list_del(&buddy->lru);
        zone->free_area[order].nr_free--;
        clear_buddy_order(buddy, order);
        
        // 合并后的块：取较小的索引
        page = min(page, buddy);
        order++;
    }
    
    // 把合并后的块放入对应 order 的空闲链表
    list_add(&page->lru, &zone->free_area[order].free_list[...]);
    zone->free_area[order].nr_free++;
    set_buddy_order(page, order);
}
```

**伙伴索引的计算**：`buddy_idx = page_idx ^ (1 << order)`

这是 Buddy System 最巧妙的设计——用 XOR 计算伙伴地址：

```
假设 order=2（块大小=4页），page_idx=8（二进制: 1000）

buddy_idx = 8 ^ 4 = 12（二进制: 1100）

page_idx=8 对应块 [8,9,10,11]
buddy_idx=12 对应块 [12,13,14,15]
合并后：块 [8..15]，order=3，page_idx=8

再找 order=3 的伙伴：
buddy_idx = 8 ^ 8 = 0（二进制: 0000）

page_idx=8 对应块 [8..15]
buddy_idx=0 对应块 [0..7]
合并后：块 [0..15]，order=4，page_idx=0
```

**XOR 的精妙之处**：在 order 层级，每个块的起始地址在该位上要么是 0 要么是 1，XOR 翻转这一位就得到伙伴的地址。

### 3.5 per-CPU 页缓存

Buddy System 的最小粒度是 1 页，但频繁分配/释放单页有开销（锁竞争、链表操作）。

per-CPU 页缓存（per-cpu pageset）的解决方案：**每个 CPU 维护一个小的空闲页列表，分配/释放单页时优先使用本地缓存，无锁操作。**

```c
struct per_cpu_pageset {
    struct per_cpu_pages pcp;
};

struct per_cpu_pages {
    int count;           // 当前缓存页数
    int high;            // 高水位（超过则归还给 buddy）
    int batch;           // 批量操作大小
    struct list_head lists[MIGRATE_PCPTYPES];  // 按迁移类型分链表
};
```

分配单页：
1. 先从 per-CPU 缓存取（无锁，快）
2. 缓存为空时，从 Buddy System 批量取 `batch` 页到缓存
3. 再从缓存取一页

释放单页：
1. 先放回 per-CPU 缓存（无锁，快）
2. 缓存超过 `high` 水位时，批量归还 `batch` 页给 Buddy System

**设计哲学：用 per-CPU 缓存消除锁竞争——空间换时间。**

---

## 四、Trade-offs：内存管理的关键权衡

### 4.1 页大小

| 页大小 | 优点 | 缺点 |
|--------|------|------|
| 4KB | 小对象浪费少、碎片小 | 大对象需要很多页、页表大 |
| 2MB (Huge Page) | 页表小、TLB 命中率高 | 内部碎片大、分配不灵活 |
| 1GB (Gigantic Page) | 极致 TLB 性能 | 极度不灵活 |

**Linux 的选择**：默认 4KB + 支持 Transparent Huge Pages（THP）+ 显式 huge page（madvise/hugetlbfs）。

### 4.2 分配器选择

| 分配器 | 优点 | 缺点 | 适用场景 |
|--------|------|------|---------|
| SLAB | 功能完整、调试友好 | 代码复杂、元数据开销大 | 大型系统 |
| SLUB | 简洁、性能好 | 调试功能较少 | 默认选择 |
| SLOB | 极简、代码量小 | 性能差 | 嵌入式系统 |

### 4.3 水位线与回收策略

```c
// zone 的三个水位线
enum zone_watermarks {
    WMARK_MIN,    // 最低水位：紧急，必须回收
    WMARK_LOW,    // 低水位：开始回收
    WMARK_HIGH,   // 高水位：停止回收
};
```

```
内存使用量 →

|<-- Free -->|WMARK_HIGH|<--  Normal  -->|WMARK_LOW|<--  Tight  -->|WMARK_MIN|<-- Critical -->|
             ↑                          ↑                       ↑
             kswapd 停止回收             kswapd 开始回收          直接回收（同步）
```

**设计哲学：用水位线实现异步回收——在内存还不太紧张时就开始回收，避免等到紧急时才同步回收（导致延迟）。**

---

## 五、Real-world Analysis：Linux 内存管理源码

### 5.1 page 结构

每个物理页框对应一个 `struct page`：

```c
// include/linux/mm_types.h
struct page {
    unsigned long flags;         // 页状态标志（PG_locked, PG_dirty, etc.）
    
    union {
        struct {                 // 页缓存使用
            struct address_space *mapping;
            pgoff_t index;
        };
        struct {                 // Buddy System 使用
            struct list_head buddy_list;
            unsigned long buddy_order;
        };
        struct {                 // slab 使用
            struct slab *slab_cache;
        };
    };
    
    union {
        atomic_t _mapcount;      // 映射计数
        unsigned int active;     // slab 使用
    };
    
    atomic_t _refcount;          // 引用计数
    
#ifdef CONFIG_MEMCG
    struct mem_cgroup *mem_cgroup; // 内存 cgroup
#endif
};
```

**设计哲学：page 是一个 union-heavy 的结构——同一个内存位置在不同状态下表示不同含义，节省内存。** 因为系统中有数百万个 page 结构，每个字节都很重要。

### 5.2 GFP 标志（Get Free Pages）

分配内存时通过 GFP 标志告诉分配器"我需要什么样的内存"：

```c
// include/linux/gfp.h
#define GFP_KERNEL    (__GFP_RECLAIM | __GFP_IO | __GFP_FS)    // 内核正常分配
#define GFP_ATOMIC    (__GFP_HIGH)                              // 原子分配（不睡眠）
#define GFP_USER      (__GFP_RECLAIM | __GFP_IO | __GFP_FS | __GFP_HARDWALL) // 用户进程
#define GFP_DMA       (__GFP_DMA)                               // DMA 区域
#define GFP_HIGHUSER  (GFP_USER | __GFP_HIGHMEM)               // 高内存区域
```

**关键区分：GFP_KERNEL vs GFP_ATOMIC**

- `GFP_KERNEL`：可以睡眠、可以触发 I/O 回收——在进程上下文中使用
- `GFP_ATOMIC`：不能睡眠——在中断处理或持锁时使用

**为什么 GFP_ATOMIC 不能睡眠？** 因为在中断处理中睡眠会导致调度器无法调度——中断上下文没有关联的进程。

### 5.3 vmalloc — 虚拟连续分配

有时内核需要大块连续的虚拟地址空间，但不要求物理连续：

```c
// mm/vmalloc.c（简化）
void *vmalloc(unsigned long size)
{
    // 1. 在 vmalloc 地址区域找一段空闲的虚拟地址范围
    void *addr = __get_vm_area_node(size, ...);
    
    // 2. 逐页分配物理页（不需要连续！）
    for (int i = 0; i < num_pages; i++) {
        struct page *page = alloc_page(GFP_KERNEL);
        // 3. 修改页表，把虚拟页映射到物理页
        map_vm_area(addr, page, ...);
    }
    
    return addr;
}
```

vmalloc 地址区域（x86-64）：
```
0xFFFF_8000_0000_0000 ~ 0xFFFF_C000_0000_0000: vmalloc/ioremap 区域
```

**vmalloc 的设计哲学：用虚拟地址连续性替代物理地址连续性——对于不需要物理连续的场景，避免了大块物理连续分配的困难。**

---

## 六、Hands-on Lab：lab03-memory-allocator

### 实验1：C 实现 Buddy System

```c
// src/mini-kernel/buddy.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define MAX_ORDER 10
#define PAGE_SIZE 4096

typedef struct {
    int order;                    // 块的 order
    int free;                     // 是否空闲
    struct block *buddy;          // 伙伴块
} block_t;

typedef struct {
    int total_pages;
    block_t *blocks;              // 所有块的数组
    struct list_head free_lists[MAX_ORDER + 1]; // 每个 order 的空闲链表
} buddy_system_t;

// 简化版 Buddy System
#define NUM_PAGES 1024  // 1024 页 = 4MB

typedef struct page {
    int order;
    int allocated;
    struct page *next;
    struct page *prev;
} page_t;

page_t pages[NUM_PAGES];
page_t *free_lists[MAX_ORDER + 1];

void buddy_init() {
    memset(pages, 0, sizeof(pages));
    for (int i = 0; i <= MAX_ORDER; i++)
        free_lists[i] = NULL;
    
    // 初始：整个内存是一个 Order 10 的块（1024页）
    pages[0].order = MAX_ORDER;
    pages[0].allocated = 0;
    free_lists[MAX_ORDER] = &pages[0];
}

page_t *buddy_alloc(int order) {
    // 从 order 开始向上查找
    for (int o = order; o <= MAX_ORDER; o++) {
        if (free_lists[o] != NULL) {
            page_t *block = free_lists[o];
            // 从链表移除
            free_lists[o] = block->next;
            if (block->next) block->next->prev = NULL;
            
            // 如果 o > order，逐级分裂
            while (o > order) {
                o--;
                int buddy_idx = (block - pages) + (1 << o);
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
    return NULL; // 分配失败
}

void buddy_free(page_t *block) {
    int order = block->order;
    block->allocated = 0;
    
    while (order < MAX_ORDER) {
        // 计算伙伴索引
        int block_idx = block - pages;
        int buddy_idx = block_idx ^ (1 << order);
        page_t *buddy = &pages[buddy_idx];
        
        // 检查伙伴是否空闲且 order 相同
        if (buddy->allocated || buddy->order != order)
            break;
        
        // 从空闲链表移除伙伴
        if (buddy->prev) buddy->prev->next = buddy->next;
        else free_lists[order] = buddy->next;
        if (buddy->next) buddy->next->prev = buddy->prev;
        
        // 合并：取较小索引
        if (buddy_idx < block_idx)
            block = buddy;
        
        order++;
        block->order = order;
    }
    
    // 放入空闲链表
    block->next = free_lists[order];
    block->prev = NULL;
    if (free_lists[order]) free_lists[order]->prev = block;
    free_lists[order] = block;
}

int main() {
    buddy_init();
    
    printf("Alloc order 2 (4 pages):\n");
    page_t *a = buddy_alloc(2);
    printf("  Block at page %ld\n", a - pages);
    
    printf("Alloc order 3 (8 pages):\n");
    page_t *b = buddy_alloc(3);
    printf("  Block at page %ld\n", b - pages);
    
    printf("Free block a:\n");
    buddy_free(a);
    
    printf("Free block b:\n");
    buddy_free(b);
    
    printf("Alloc order 10 (all pages):\n");
    page_t *c = buddy_alloc(10);
    printf("  Block at page %ld, %s\n", c - pages, c ? "success" : "failed");
    
    return 0;
}
```

### 实验2：Python Buddy System 可视化

```python
# src/simulators/buddy_visualizer.py
class BuddySystem:
    def __init__(self, max_order=10):
        self.max_order = max_order
        self.total_pages = 1 << max_order
        self.free_lists = {i: [] for i in range(max_order + 1)}
        # 初始：一个最大的块
        self.free_lists[max_order] = [0]  # 起始页索引
        self.allocated = {}  # page_idx -> order
    
    def alloc(self, order):
        for o in range(order, self.max_order + 1):
            if self.free_lists[o]:
                block = self.free_lists[o].pop(0)
                # 分裂
                while o > order:
                    o -= 1
                    buddy = block + (1 << o)
                    self.free_lists[o].append(buddy)
                self.allocated[block] = order
                return block
        return None
    
    def free(self, block):
        order = self.allocated.pop(block)
        while order < self.max_order:
            buddy = block ^ (1 << order)
            if buddy in self.allocated or buddy not in self._flatten_free(order):
                break
            # 合并
            self.free_lists[order].remove(buddy)
            block = min(block, buddy)
            order += 1
        self.free_lists[order].append(block)
    
    def _flatten_free(self, order):
        return self.free_lists[order]
    
    def visualize(self):
        for o in range(self.max_order + 1):
            if self.free_lists[o]:
                size = 1 << o
                print(f"Order {o} ({size} pages): {self.free_lists[o]}")
        if self.allocated:
            print(f"Allocated: {self.allocated}")

if __name__ == "__main__":
    bs = BuddySystem(max_order=6)  # 64 pages
    print("=== Initial state ===")
    bs.visualize()
    
    a = bs.alloc(2)
    print(f"\n=== After alloc order 2 at page {a} ===")
    bs.visualize()
    
    b = bs.alloc(3)
    print(f"\n=== After alloc order 3 at page {b} ===")
    bs.visualize()
    
    bs.free(a)
    print(f"\n=== After free page {a} ===")
    bs.visualize()
    
    bs.free(b)
    print(f"\n=== After free page {b} ===")
    bs.visualize()
```

### 进阶实验

- 在 Buddy System 上实现简单的 slab allocator
- 添加 per-CPU 缓存层
- 实现内存碎片整理（compaction）模拟

---

## 参考资源

- Linux 源码 `mm/page_alloc.c` — Buddy System 实现
- Linux 源码 `mm/slub.c` — SLUB 分配器实现
- Linux 源码 `mm/vmalloc.c` — vmalloc 实现
- *Understanding the Linux Kernel* Ch.8 — 内存管理
- *Linux Kernel Development* Ch.12 — 内存管理
- Buddy System 原始论文：*A fast storage allocator* (Knowlton, 1965)
- Slab Allocator 论文：*The Slab Allocator: An Object-Caching Kernel Memory Allocator* (Bonwick, 1994)