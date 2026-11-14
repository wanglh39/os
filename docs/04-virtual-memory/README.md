# 04 - 虚拟内存

> "Virtual memory is one of the most elegant abstractions in computer science — it creates the illusion that each process has its own private, contiguous address space."

---

## 一、Design Philosophy：虚拟内存在解决什么问题？

### 1.1 没有虚拟内存的世界

如果程序直接使用物理地址：

```c
// 程序 A 的代码
int *data = (int *)0x10000;  // 直接使用物理地址

// 程序 B 的代码
int *data = (int *)0x10000;  // 也使用同一个物理地址！
```

问题：
1. **地址冲突**：两个程序使用了相同的地址，互相覆盖数据
2. **无法重定位**：程序必须知道自己在物理内存中的位置
3. **无法扩展**：程序大小受限于物理内存大小
4. **安全缺失**：任何程序都可以读写任何物理地址

### 1.2 虚拟内存的三个核心承诺

虚拟内存通过**地址翻译**机制，为每个进程提供三个承诺：

1. **隔离**：每个进程有独立的地址空间，互不干扰
2. **连续**：每个进程的地址空间从 0 开始，连续且完整
3. **无限**：虚拟地址空间远大于物理内存（通过交换/换页实现）

```
进程A的虚拟地址空间:        物理内存:
┌─────────────┐            ┌─────────────┐
│ 0x0000_0000 │ ──┐    ┌──→ │ Frame 5     │
│   ...       │   │    │    │ Frame 6     │
│ 0x4000_0000 │ ──┼────┼──→ │ Frame 12    │
│   (code)    │   │    │    │ Frame 13    │
│ 0x6000_0000 │ ──┘    │    │ ...         │
│   (data)    │        │    │ Frame 100   │
│ ...         │        ├──→ │ Frame 101   │
│ 0x7fff_ffff │        │    │ ...         │
└─────────────┘        │    └─────────────┘
                       │
进程B的虚拟地址空间:        │
┌─────────────┐            │
│ 0x0000_0000 │ ──────────→│ Frame 200
│   ...       │            │ Frame 201
│ 0x4000_0000 │ ──────────→│ Frame 50
│   (code)    │            │ ...
│ 0x6000_0000 │ ──────────→│ Frame 80
│   (data)    │            │
│ ...         │            │
│ 0x7fff_ffff │            │
└─────────────┘
```

**设计哲学：间接层（indirection）——在地址访问和物理内存之间插入翻译层，用翻译层实现隔离、重定位和扩展。**

David Wheeler 的名言："All problems in computer science can be solved by another level of indirection."

---

## 二、Historical Evolution：虚拟内存的演进

### 2.1 覆盖（Overlay）—— 虚拟内存的前身（1960s）

在虚拟内存出现之前，程序大于物理内存时使用"覆盖"技术：

```
程序总大小 64KB，物理内存只有 32KB：

┌──────────────┐
│ 常驻部分     │ 8KB  ← 始终在内存
├──────────────┤
│ Overlay A    │ 24KB ← 需要时加载，覆盖 Overlay B
│ Overlay B    │ 24KB ← 需要时加载，覆盖 Overlay A
└──────────────┘
```

程序员必须**手动**管理覆盖的加载和切换——极其痛苦且容易出错。

### 2.2 分页虚拟内存（1960s, Atlas 计算机）

Manchester 大学的 Atlas 计算机首次实现了分页虚拟内存：

- 把虚拟地址空间分成固定大小的**页**
- 把物理内存分成同样大小的**页框**
- 用**页表**记录虚拟页到物理页框的映射
- 不在内存中的页存储在磁盘上，需要时加载（**按需分页**）

这是计算机科学史上最重要的发明之一。

### 2.3 多级页表（1980s-）

32位地址空间需要 4MB 的页表（1M 页 × 4字节/条目）。如果每个进程都有 4MB 页表，100 个进程就是 400MB——不可接受。

多级页表的解决方案：**只保存实际使用的地址范围的页表项。**

```
32位地址，2级页表：
- 页目录（1K条目 × 4字节 = 4KB）
- 页表（1K条目 × 4字节 = 4KB）

如果进程只用了 8MB 地址空间（2个页目录项）：
- 1个页目录（4KB）+ 2个页表（8KB）= 12KB
- 而不是 4MB！
```

### 2.4 64位地址空间与五级页表

x86-64 使用 48 位虚拟地址（256TB 地址空间），需要四级页表：

```
48位地址: [9位 PML4][9位 PDP][9位 PD][9位 PT][12位 Offset]
         ↓           ↓        ↓       ↓       ↓
         4级         3级      2级     1级     页内偏移
         (PGD)       (PUD)    (PMD)   (PTE)
```

Linux 5.x 引入了五级页表（57位地址空间，128PB）：

```
57位地址: [9位 PML5][9位 PML4][9位 PDP][9位 PD][9位 PT][12位 Offset]
```

**为什么每级 9 位？** 因为每级页表占 1 页（4KB），每个条目 8 字节（64位），4KB / 8B = 512 = 2^9 条目。

---

## 三、Core Mechanism：页表与地址翻译

### 3.1 页表条目（PTE）

```c
// x86-64 的 PTE 格式（64位）
// Bit 63: NX (No Execute)
// Bit 62-52: Available for OS
// Bit 51-12: Physical Frame Number (40 bits → 1TB physical addressable)
// Bit 11-9: Available for OS
// Bit 8: G (Global TLB)
// Bit 7: PAT (Page Attribute Table)
// Bit 6: D (Dirty - written to)
// Bit 5: A (Accessed - read or written)
// Bit 4: PCD (Page-level Cache Disable)
// Bit 3: PWT (Page-level Write-Through)
// Bit 2: U/S (User/Supervisor)
// Bit 1: R/W (Read/Write)
// Bit 0: P (Present)
```

关键标志位：

| 标志 | 含义 | 为什么需要 |
|------|------|-----------|
| P (Present) | 页是否在物理内存中 | 不在则触发缺页异常 |
| R/W | 读/写权限 | 写保护（COW、只读代码段） |
| U/S | 用户/内核权限 | 隔离内核地址空间 |
| A (Accessed) | 是否被访问过 | 页面置换算法使用 |
| D (Dirty) | 是否被写入 | 决定换出时是否需要写回磁盘 |
| NX | 不可执行 | 防止代码注入攻击 |

### 3.2 地址翻译的完整流程

```
CPU 发出虚拟地址 0x00007F8A_B123_4567
                    │
                    ▼
┌─────────────────────────────────────────────┐
│ 1. CR3 寄存器 → 当前进程的 PML4 表物理地址   │
│                                              │
│ 2. 从虚拟地址提取 PML4 索引 (bits 47-39)     │
│    → 查 PML4 表 → PDP 表物理地址             │
│                                              │
│ 3. 从虚拟地址提取 PDP 索引 (bits 38-30)      │
│    → 查 PDP 表 → PD 表物理地址               │
│                                              │
│ 4. 从虚拟地址提取 PD 索引 (bits 29-21)       │
│    → 查 PD 表 → PT 表物理地址                │
│                                              │
│ 5. 从虚拟地址提取 PT 索引 (bits 20-12)       │
│    → 查 PT 表 → 物理页框地址                 │
│                                              │
│ 6. 物理页框地址 + 页内偏移 (bits 11-0)       │
│    → 最终物理地址                            │
└─────────────────────────────────────────────┘
```

每次地址翻译需要 4 次内存访问（4 级页表）——如果没有缓存，性能灾难。

### 3.3 TLB — Translation Lookaside Buffer

TLB 是 CPU 内部的硬件缓存，缓存最近使用的页表条目：

```
TLB 命中：
  虚拟地址 → TLB 查找 → 直接得到物理地址（1 cycle）

TLB 未命中：
  虚拟地址 → 走 4 级页表（4 次内存访问） → 物理地址
  → 同时更新 TLB
```

TLB 的容量很小（通常 64-1024 条目），但命中率很高（>99%），因为程序有**局部性**——访问的地址往往集中在少数几个页。

**TLB 刷新的代价**：

切换进程时需要刷新 TLB（因为新进程有不同的页表），这会导致切换后的大量 TLB miss。

**优化1：PCID（Process Context Identifier）**——在 TLB 条目中标记进程 ID，切换进程时不刷新属于其他进程的 TLB 条目。

**优化2：全局页（Global Page）**——内核地址空间在所有进程间共享，标记为 Global 的 TLB 条目在进程切换时不刷新。

### 3.4 缺页异常（Page Fault）

当 PTE 的 P 位为 0（页不在物理内存中），CPU 触发缺页异常：

```c
// arch/x86/mm/fault.c（简化）
void do_page_fault(struct pt_regs *regs, unsigned long error_code)
{
    unsigned long address = read_cr2();  // 获取导致缺页的虚拟地址
    
    // 判断缺页类型
    if (error_code & PF_USER) {
        // 用户态缺页
        handle_user_mode_fault(address, error_code);
    } else {
        // 内核态缺页
        handle_kernel_mode_fault(address, error_code);
    }
}
```

缺页的四种情况：

| 情况 | P 位 | 原因 | 处理方式 |
|------|------|------|---------|
| 页不在内存 | 0 | 页被换出到磁盘 | 从磁盘加载到内存，更新 PTE |
| 首次访问 | 0 | 页从未被分配 | 分配新物理页（零初始化） |
| COW 页 | 1, R/W=0 | 写只读页（COW） | 分配新页，复制内容，更新 PTE |
| 权限违反 | 1 | 用户态访问内核页 | 发送 SIGSEGV |

### 3.5 写时复制（COW）的详细流程

```
1. fork() 时：
   父进程的页都标记为只读（R/W=0）
   子进程共享父进程的页（PTE 指向同一物理页框）

2. 父进程或子进程写入某页：
   → 触发缺页异常（写只读页）
   → 内核检查：这是 COW 页吗？
   → 是：分配新物理页，复制内容，修改 PTE 为可写
   → 不是：发送 SIGSEGV

3. 结果：
   只有被写入的页才被复制
   只读的页继续共享
```

```c
// mm/memory.c（简化）
static vm_fault_t handle_pte_fault(struct vm_fault *vmf)
{
    pte_t entry = *vmf->pte;
    
    if (!pte_present(entry)) {
        // 页不在内存
        if (pte_none(entry))
            return do_anonymous_page(vmf);  // 首次访问
        else
            return do_swap_page(vmf);       // 从磁盘换入
    }
    
    if (vmf->flags & FAULT_FLAG_WRITE) {
        if (!pte_write(entry))
            return do_wp_page(vmf);         // COW 处理
        // ...
    }
    
    return 0;
}

static vm_fault_t do_wp_page(struct vm_fault *vmf)
{
    struct page *old_page = vmf->page;
    
    // 如果只有一个引用，直接改为可写
    if (page_count(old_page) == 1) {
        wp_page_reuse(vmf);
        return 0;
    }
    
    // 多个引用（被共享），需要复制
    struct page *new_page = alloc_page(GFP_HIGHUSER);
    copy_user_highpage(new_page, old_page, vmf->address, vmf->vma);
    
    // 更新 PTE 指向新页，标记可写
    pte_t entry = mk_pte(new_page, vmf->vma->vm_page_prot);
    entry = pte_mkdirty(entry);
    entry = pte_mkwrite(entry);
    set_pte_at(vmf->vma->vm_mm, vmf->address, vmf->pte, entry);
    
    // 减少旧页的引用计数
    put_page(old_page);
    
    return 0;
}
```

---

## 四、页面置换算法

### 4.1 为什么需要页面置换？

物理内存有限，但虚拟地址空间远大于物理内存。当物理内存满了，需要把一些页换出到磁盘，腾出空间给新页。

**核心问题：选择哪个页换出？**

理想：换出"最长时间不会被访问"的页（Belady 最优算法，但无法实现——无法预知未来）。

### 4.2 常见算法

#### FIFO（先进先出）

```
物理内存（3页框）：

访问序列: 7, 0, 1, 2, 0, 3, 0, 4

Step 1: [7]          miss
Step 2: [7,0]        miss
Step 3: [7,0,1]      miss
Step 4: [0,1,2]      miss (换出7)
Step 5: [0,1,2]      hit
Step 6: [1,2,3]      miss (换出0)
Step 7: [2,3,0]      miss (换出1)
Step 8: [3,0,4]      miss (换出2)

命中率: 1/8 = 12.5%
```

问题：FIFO 可能换出频繁使用的页。而且 FIFO 存在 **Belady 异常**——增加页框数反而降低命中率！

#### LRU（最近最少使用）

```
访问序列: 7, 0, 1, 2, 0, 3, 0, 4

Step 1: [7]          miss
Step 2: [7,0]        miss
Step 3: [7,0,1]      miss
Step 4: [0,1,2]      miss (换出7，最久未用)
Step 5: [1,2,0]      hit  (0移到最新)
Step 6: [2,0,3]      miss (换出1)
Step 7: [2,3,0]      hit  (0移到最新)
Step 8: [3,0,4]      miss (换出2)

命中率: 2/8 = 25%
```

LRU 是理论上的好算法，但**精确实现 LRU 代价很高**——需要每次访问都更新顺序，硬件支持有限。

#### Clock 算法（二次机会）

Linux 实际使用的近似 LRU 算法。利用 PTE 的 A（Accessed）位：

```
所有页组织成环形链表，有一个"指针"指向当前位置：

     ┌──→ [Page A: A=0] → [Page B: A=1] → [Page C: A=0] → [Page D: A=1] ──┐
     └──────────────────────────────────────────────────────────────────────┘

需要换出页时：
1. 指针指向 Page A，A=0 → 换出 Page A
2. 如果 A=1 → 清零 A，指针前进（给"第二次机会"）
3. 重复直到找到 A=0 的页
```

**设计哲学：用硬件提供的 A 位近似 LRU——不需要精确的访问顺序，只需要区分"最近访问过"和"最近没访问过"。**

#### Linux 的双指针 Clock（Active/Inactive 链表）

Linux 进一步改进，使用两个链表：

```
Active 链表（最近活跃的页）: [Page A] → [Page B] → [Page C]
Inactive 链表（最近不活跃的页）: [Page D] → [Page E] → [Page F]

新页 → 加入 Inactive 链表头部
Inactive 中的页被再次访问 → 提升到 Active 链表
Active 链表中的页长期不被访问 → 降级到 Inactive 链表
换出时 → 从 Inactive 链表尾部选择
```

```c
// mm/vmscan.c（简化）
struct lruvec {
    struct list_head lists[NR_LRU_LISTS];
    // ...
};

enum lru_list {
    LRU_INACTIVE_ANON,    // 不活跃匿名页
    LRU_ACTIVE_ANON,      // 活跃匿名页
    LRU_INACTIVE_FILE,    // 不活跃文件页
    LRU_ACTIVE_FILE,      // 活跃文件页
    LRU_UNEVICTABLE,      // 不可换出
};
```

**为什么区分匿名页和文件页？** 因为文件页可以直接从磁盘重新加载（丢弃即可），而匿名页必须写入 swap 才能换出（代价更大）。所以优先换出文件页。

---

## 五、Trade-offs：虚拟内存的关键权衡

### 5.1 页大小 vs 页表大小

| 页大小 | 页表大小（48位地址） | TLB 覆盖范围 | 内部碎片 |
|--------|---------------------|-------------|---------|
| 4KB | 512GB / 4KB × 8B = 1GB | 512 × 4KB = 2MB | 小 |
| 2MB | 512GB / 2MB × 8B = 2MB | 512 × 2MB = 1GB | 中 |
| 1GB | 512GB / 1GB × 8B = 4KB | 512 × 1GB = 512GB | 大 |

**权衡**：大页减少页表大小和 TLB miss，但增加内部碎片和分配难度。

### 5.2 按需分页 vs 预加载

| 方案 | 优点 | 缺点 |
|------|------|------|
| 按需分页（Demand Paging） | 只加载实际使用的页、启动快 | 频繁缺页中断、运行中延迟 |
| 预加载（Prefetch） | 减少运行中缺页 | 可能加载不需要的页、浪费内存 |

**Linux 的选择**：按需分页为主 + readahead 预读（文件页）。

### 5.3 Swap vs OOM

当物理内存耗尽：

| 方案 | 优点 | 缺点 |
|------|------|------|
| Swap（换出到磁盘） | 给进程更多时间、避免杀进程 | 磁盘 I/O 慢、系统可能 thrashing |
| OOM Killer（杀进程） | 立即释放内存、避免 thrashing | 杀掉用户进程、数据丢失 |

**Linux 的选择**：先 Swap，Swap 不够时 OOM Killer。OOM Killer 的选择策略基于进程的"坏度"（oom_score）——内存占用大、优先级低的进程优先被杀。

---

## 六、Real-world Analysis：Linux 虚拟内存源码

### 6.1 mm_struct — 进程地址空间

```c
// include/linux/mm_types.h
struct mm_struct {
    struct {
        struct maple_tree mm_mt;     // Maple tree（新内核，替代红黑树）
        unsigned long mmap_base;     // mmap 区域基址
        unsigned long mmap_legacy_base;
        unsigned long task_size;     // 进程地址空间大小
        pgd_t *pgd;                  // 页全局目录（顶级页表）
        
        atomic_t mm_users;           // 用户计数（线程共享时增加）
        atomic_t mm_count;           // 引用计数
        
        int map_count;               // VMA 数量
        
        spinlock_t arg_lock;
        unsigned long start_code, end_code;   // 代码段
        unsigned long start_data, end_data;   // 数据段
        unsigned long start_brk, brk;         // 堆
        unsigned long start_stack;            // 栈
        unsigned long arg_start, arg_end;     // 命令行参数
        unsigned long env_start, env_end;     // 环境变量
    };
    
    // ...
};
```

### 6.2 VMA — 虚拟内存区域

每个连续的虚拟地址范围对应一个 VMA（Virtual Memory Area）：

```c
struct vm_area_struct {
    unsigned long vm_start;          // 起始虚拟地址
    unsigned long vm_end;            // 结束虚拟地址
    unsigned long vm_flags;          // 属性（VM_READ, VM_WRITE, VM_EXEC, VM_SHARED）
    struct rb_node vm_rb;            // 红黑树节点（按地址排序）
    struct mm_struct *vm_mm;         // 所属地址空间
    struct file *vm_file;            // 映射的文件（如果有）
    unsigned long vm_pgoff;          // 文件内偏移（以页为单位）
    const struct vm_operations_struct *vm_ops; // 操作函数表
    // ...
};
```

VMA 的组织（新内核用 Maple Tree 替代红黑树）：

```
进程的虚拟地址空间（通过 VMA 描述）：

0x0000_0000 ──────────────────────────────
              │ (未使用)                  │
0x4000_0000 ──┤ VMA: code (r-x)           │
              │ VMA: data (rw-)           │
0x6000_0000 ──┤ VMA: heap (rw-, grow up)  │ ← brk
              │ (未使用)                  │
0x7f00_0000 ──┤ VMA: mmap (rw-)           │ ← mmap 区域
              │ VMA: stack (rw-, grow down)│
0x7fff_ffff ──┴───────────────────────────
```

### 6.3 x86-64 地址空间布局

```
0x0000_0000_0000_0000 ────────────────────────────────────
                        │ User Space                     │
                        │ (47位地址空间, 256TB)           │
0x0000_7fff_ffff_ffff ──┴────────────────────────────────
                        │ Non-canonical (hole)            │
0xffff_8000_0000_0000 ────────────────────────────────────
                        │ Kernel Space                    │
                        │ - Direct mapping (物理内存直接映射)│
                        │ - vmalloc/ioremap               │
                        │ - Kernel text/data              │
0xffff_ffff_ffff_ffff ──┴────────────────────────────────
```

**关键设计**：内核地址空间在所有进程间共享——切换进程时不需要切换内核部分的页表。只有用户空间的页表是每个进程独立的。

---

## 七、Hands-on Lab：lab04-page-table

### 实验1：Python 页表翻译模拟器

```python
# src/simulators/page_table_sim.py

class PageTableEntry:
    def __init__(self):
        self.frame = None       # 物理页框号
        self.present = False    # 是否在内存中
        self.readable = True
        self.writable = True
        self.executable = True
        self.user = True
        self.accessed = False   # A 位
        self.dirty = False      # D 位

class MultiLevelPageTable:
    """模拟 x86-64 四级页表"""
    def __init__(self, levels=4, bits_per_level=9, page_offset_bits=12):
        self.levels = levels
        self.bits_per_level = bits_per_level
        self.page_offset_bits = page_offset_bits
        self.root = {}  # 嵌套字典模拟多级页表
        self.physical_memory = {}  # frame_num -> data
    
    def _extract_indices(self, vaddr):
        """从虚拟地址提取各级索引"""
        offset = vaddr & ((1 << self.page_offset_bits) - 1)
        vaddr >>= self.page_offset_bits
        indices = []
        for _ in range(self.levels):
            indices.append(vaddr & ((1 << self.bits_per_level) - 1))
            vaddr >>= self.bits_per_level
        indices.reverse()  # 从最高级到最低级
        return indices, offset
    
    def map(self, vaddr, frame, flags=None):
        """建立虚拟地址到物理页框的映射"""
        indices, offset = self._extract_indices(vaddr)
        node = self.root
        for i in range(self.levels - 1):
            if indices[i] not in node:
                node[indices[i]] = {}
            node = node[indices[i]]
        
        entry = PageTableEntry()
        entry.frame = frame
        entry.present = True
        if flags:
            entry.readable = flags.get('readable', True)
            entry.writable = flags.get('writable', True)
            entry.executable = flags.get('executable', True)
        node[indices[-1]] = entry
    
    def translate(self, vaddr, access_type='read'):
        """翻译虚拟地址到物理地址"""
        indices, offset = self._extract_indices(vaddr)
        
        # 走多级页表
        node = self.root
        for i in range(self.levels - 1):
            if indices[i] not in node:
                return None, "Page table not found (level {})".format(i)
            node = node[indices[i]]
        
        if indices[-1] not in node:
            return None, "PTE not found"
        
        entry = node[indices[-1]]
        
        if not entry.present:
            return None, "Page not present (Page Fault!)"
        
        # 权限检查
        if access_type == 'write' and not entry.writable:
            return None, "Write protection fault (COW?)"
        if access_type == 'execute' and not entry.executable:
            return None, "Execute protection fault (NX)"
        
        # 更新 A/D 位
        entry.accessed = True
        if access_type == 'write':
            entry.dirty = True
        
        # 计算物理地址
        phys_addr = (entry.frame << self.page_offset_bits) | offset
        return phys_addr, "OK"

if __name__ == "__main__":
    pt = MultiLevelPageTable()
    
    # 映射虚拟页 0x1000 到物理页框 0x500
    pt.map(0x1000, 0x500, {'writable': False})  # 只读页（模拟 COW）
    pt.map(0x2000, 0x800, {'executable': False})  # 不可执行页
    pt.map(0x3000, 0xA00)  # 正常页
    
    # 测试翻译
    print("Read 0x1000:", pt.translate(0x1000, 'read'))
    print("Write 0x1000:", pt.translate(0x1000, 'write'))  # 应该触发写保护
    print("Execute 0x2000:", pt.translate(0x2000, 'execute'))  # 应该触发 NX
    print("Read 0x4000:", pt.translate(0x4000, 'read'))  # 应该缺页
    print("Write 0x3000:", pt.translate(0x3000, 'write'))  # 正常写入
```

### 实验2：Python 页面置换算法模拟

```python
# src/simulators/page_replacement_sim.py
from collections import deque, OrderedDict

def fifo_replacement(access_sequence, num_frames):
    frames = deque()
    page_set = set()
    hits = 0
    misses = 0
    
    for page in access_sequence:
        if page in page_set:
            hits += 1
        else:
            misses += 1
            if len(frames) >= num_frames:
                evicted = frames.popleft()
                page_set.remove(evicted)
            frames.append(page)
            page_set.add(page)
    
    return hits, misses

def lru_replacement(access_sequence, num_frames):
    cache = OrderedDict()  # page -> True, 按访问顺序排列
    hits = 0
    misses = 0
    
    for page in access_sequence:
        if page in cache:
            hits += 1
            cache.move_to_end(page)  # 移到最新
        else:
            misses += 1
            if len(cache) >= num_frames:
                cache.popitem(last=False)  # 淘汰最久未用
            cache[page] = True
    
    return hits, misses

def clock_replacement(access_sequence, num_frames):
    frames = [None] * num_frames
    referenced = [False] * num_frames
    pointer = 0
    hits = 0
    misses = 0
    
    for page in access_sequence:
        if page in frames:
            hits += 1
            referenced[frames.index(page)] = True  # 设置引用位
        else:
            misses += 1
            # Clock 算法：找 referenced=False 的页
            while referenced[pointer]:
                referenced[pointer] = False  # 给第二次机会
                pointer = (pointer + 1) % num_frames
            # 换出
            frames[pointer] = page
            referenced[pointer] = True
            pointer = (pointer + 1) % num_frames
    
    return hits, misses

if __name__ == "__main__":
    seq = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
    frames = 3
    
    print(f"Access sequence: {seq}")
    print(f"Frames: {frames}\n")
    
    h, m = fifo_replacement(seq, frames)
    print(f"FIFO:  hits={h}, misses={m}, hit_rate={h/(h+m)*100:.1f}%")
    
    h, m = lru_replacement(seq, frames)
    print(f"LRU:   hits={h}, misses={m}, hit_rate={h/(h+m)*100:.1f}%")
    
    h, m = clock_replacement(seq, frames)
    print(f"Clock: hits={h}, misses={m}, hit_rate={h/(h+m)*100:.1f}%")
```

### 进阶实验

- 实现 Linux 的 Active/Inactive 双链表页面置换
- 模拟 COW：fork 后父子进程共享页，写入时复制
- 模拟 TLB：实现 TLB 缓存，统计 TLB miss rate
- 测试 Belady 异常：FIFO 在增加页框时命中率下降

---

## 参考资源

- Linux 源码 `mm/memory.c` — 缺页处理、COW
- Linux 源码 `mm/vmscan.c` — 页面回收
- Linux 源码 `arch/x86/mm/` — x86 页表操作
- *Operating Systems: Three Easy Pieces* — 虚拟内存章节（免费在线）
- *Understanding the Linux Kernel* Ch.9 — 内存寻址
- Intel SDM Vol.3 Ch.4 — 页表和地址翻译的硬件规范