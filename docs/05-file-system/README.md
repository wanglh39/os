# 05 - 文件系统

> "Everything is a file." — Unix philosophy

---

## 一、Design Philosophy：文件系统在解决什么问题？

### 1.1 核心问题

磁盘/SSD 提供的是**块设备**接口——读写固定大小的数据块（通常 512 字节或 4KB）。但用户和应用程序需要的是：

1. **命名**：用名字而不是块号来访问数据
2. **组织**：把相关数据组织在一起（文件）
3. **层次**：用目录层次组织文件
4. **保护**：控制谁可以读写哪些文件
5. **持久**：数据在断电后仍然存在
6. **并发**：多个进程可以同时访问文件

**文件系统的本质：在块设备之上建立"文件"和"目录"的抽象，让用户不需要关心数据存储在哪个物理块。**

### 1.2 "一切皆文件"的设计哲学

Unix 的核心设计原则之一：

```
普通文件    → open/read/write/close
设备        → open/read/write/close（同一套接口！）
管道        → open/read/write/close
网络 socket → 虽然有专门 API，但仍有 fd
procfs      → open/read/write/close
sysfs       → open/read/write/close
```

**为什么"一切皆文件"是好设计？**

1. **统一接口**：学会一套 API 就能操作所有资源
2. **可组合**：管道 `|` 把一个程序的输出连接到另一个程序的输入
3. **工具复用**：`cat`、`grep`、`wc` 可以用于任何"文件"——设备、管道、procfs
4. **权限统一**：文件权限模型适用于所有资源

**但"一切皆文件"也有泄漏**：
- `seek()` 对管道和 socket 无意义
- `mmap()` 对字符设备无意义
- 网络 socket 需要 `send()`/`recv()` 而不是 `read()`/`write()`

**Linux 的态度：统一接口作为默认范式，允许例外存在。**

---

## 二、Historical Evolution：文件系统的演进

### 2.1 早期文件系统

最早的文件系统非常简单：

```
磁盘布局：
┌──────────┬──────────┬──────────┐
│ Superblock │ Inode表   │ 数据块    │
│ (1块)      │ (N块)     │ (剩余)    │
└──────────┴──────────┴──────────┘
```

问题：没有目录——所有文件在同一层级。

### 2.2 Unix 文件系统（UFS, 1970s）

Unix 引入了几个革命性的设计：

1. **inode**：每个文件有一个 inode（索引节点），存储文件的所有元数据
2. **目录**：目录是特殊的文件，内容是文件名→inode号的映射
3. **层次结构**：目录可以嵌套，形成树形结构
4. **硬链接**：多个文件名可以指向同一个 inode

```
目录文件的内容：
┌─────────────┬────────┐
│ 文件名       │ inode号 │
├─────────────┼────────┤
│ "hello.c"    │ 42     │
│ "Makefile"   │ 43     │
│ "src"        │ 44     │ ← src 是子目录
└─────────────┴────────┘
```

### 2.3 ext2 — Linux 的经典文件系统（1993）

ext2 是 Linux 早期最广泛使用的文件系统，奠定了 ext 系列的基础：

```
磁盘布局（Block Group）：
┌─────────────────────────────────────────────────┐
│ Block Group 0                                    │
│ ┌─────────┬──────────┬──────────┬──────────┬───┐│
│ │Superblk │ Block Grp│ Block    │ Inode    │Data││
│ │         │ Desc     │ Bitmap   │ Bitmap   │    ││
│ └─────────┴──────────┴──────────┴──────────┴───┘│
├─────────────────────────────────────────────────┤
│ Block Group 1                                    │
│ ...                                              │
└─────────────────────────────────────────────────┘
```

**Block Group 的设计哲学：把相关的元数据和数据放在一起——减少磁盘寻道距离。**

### 2.4 ext3/ext4 — 日志文件系统

ext2 的问题：断电后文件系统可能不一致（元数据更新到一半）。

ext3 的解决方案：**日志（Journal）**——把元数据修改先写入日志区，然后再修改实际数据。

```
1. 开始事务 → 写日志区："我要修改 inode 42"
2. 修改实际 inode 42
3. 提交事务 → 写日志区："事务完成"

如果断电：
- 日志有"开始"但没有"提交" → 回滚（撤销修改）
- 日志有"提交" → 重做（确保修改完成）
```

ext4 的关键改进：
- **Extent** 替代间接块——大文件不需要多级间接寻址
- **延迟分配**——写入时不立即分配块，积累后批量分配
- **多块分配**——一次分配多个连续块
- **校验和**——检测数据损坏

### 2.5 其他重要文件系统

| FS | 设计重点 | 适用场景 |
|----|---------|---------|
| XFS | 高性能、大文件、并行 I/O | 大型服务器、数据库 |
| Btrfs | Copy-on-Write、快照、校验 | 数据完整性要求高 |
| ZFS | 端到端校验、快照、池化 | 存储服务器（非 Linux 原生） |
| F2FS | 闪存友好（日志结构） | SSD、手机 |
| NFS | 网络透明访问 | 分布式环境 |

---

## 三、Core Mechanism：VFS 与 inode

### 3.1 VFS — 虚拟文件系统

VFS（Virtual File System）是 Linux 文件系统的核心抽象层：

```
应用程序
  │
  ↓
┌─────────────────────────────────────────┐
│  VFS (Virtual File System)              │ ← 统一接口
│  - open(), read(), write(), close()     │
│  - 统一的 inode/dentry/file 抽象        │
├─────────────────────────────────────────┤
│  ext4 │ XFS │ Btrfs │ NFS │ procfs │... │ ← 具体文件系统
├─────────────────────────────────────────┤
│  Block Device Layer                     │ ← 块设备层
│  - 磁盘、SSD、RAID、LVM                 │
└─────────────────────────────────────────┘
```

VFS 的核心思想：**定义一组通用接口，每个具体文件系统实现这些接口。** 上层代码不需要知道底层是 ext4 还是 NFS。

### 3.2 VFS 的四大核心对象

```c
// 1. superblock — 文件系统实例
struct super_block {
    dev_t s_dev;                    // 设备号
    unsigned long s_blocksize;      // 块大小
    unsigned long s_flags;          // 挂载标志
    struct file_system_type *s_type; // 文件系统类型
    const struct super_operations *s_op; // 操作函数表
    struct dentry *s_root;          // 根目录
    // ...
};

// 2. inode — 文件/目录的元数据
struct inode {
    umode_t i_mode;                 // 文件类型和权限
    unsigned long i_ino;            // inode 号
    uid_t i_uid;                    // 所有者
    gid_t i_gid;                    // 所属组
    loff_t i_size;                  // 文件大小
    struct timespec i_atime;        // 最后访问时间
    struct timespec i_mtime;        // 最后修改时间
    struct timespec i_ctime;        // 最后状态改变时间
    const struct inode_operations *i_op; // inode 操作
    const struct file_operations *i_fop; // 文件操作
    struct address_space *i_mapping; // 页缓存
    // ...
};

// 3. dentry — 目录项（路径分量）
struct dentry {
    struct qstr d_name;             // 名称
    struct inode *d_inode;          // 关联的 inode
    struct dentry *d_parent;        // 父目录
    struct list_head d_subdirs;     // 子目录链表
    const struct dentry_operations *d_op;
    // ...
};

// 4. file — 打开的文件实例
struct file {
    struct path f_path;             // 路径（dentry + vfsmount）
    const struct file_operations *f_op; // 操作函数表
    unsigned int f_flags;           // 打开标志（O_RDONLY 等）
    loff_t f_pos;                   // 当前读写位置
    void *private_data;             // 私有数据
    // ...
};
```

**四个对象的关系**：

```
路径 "/home/user/file.txt" 的解析过程：

1. 从根 dentry (/) 开始
2. 查找子目录 "home" → 得到 dentry(home)
3. 查找子目录 "user" → 得到 dentry(user)
4. 查找文件 "file.txt" → 得到 dentry(file.txt)
5. dentry(file.txt) → inode → file（打开后）

superblock ←→ inode ←→ dentry ←→ file
  (文件系统)  (文件元数据) (路径分量) (打开实例)
```

**设计哲学：分离"文件是什么"（inode）和"文件叫什么"（dentry）——同一个 inode 可以有多个名字（硬链接）。**

### 3.3 inode 的操作函数表

```c
struct inode_operations {
    int (*create)(struct inode *, struct dentry *, umode_t, bool);  // 创建文件
    struct dentry *(*lookup)(struct inode *, struct dentry *, unsigned int); // 查找
    int (*link)(struct dentry *, struct inode *, struct dentry *);  // 硬链接
    int (*unlink)(struct inode *, struct dentry *);                 // 删除
    int (*mkdir)(struct inode *, struct dentry *, umode_t);         // 创建目录
    int (*rmdir)(struct inode *, struct dentry *);                  // 删除目录
    int (*rename)(struct inode *, struct dentry *, struct inode *, struct dentry *); // 重命名
    int (*setattr)(struct dentry *, struct iattr *);                // 修改属性
    int (*getattr)(const struct path *, struct kstat *, u32, unsigned int); // 获取属性
    // ...
};

struct file_operations {
    loff_t (*llseek)(struct file *, loff_t, int);                   // seek
    ssize_t (*read)(struct file *, char __user *, size_t, loff_t *); // read
    ssize_t (*write)(struct file *, const char __user *, size_t, loff_t *); // write
    int (*mmap)(struct file *, struct vm_area_struct *);            // mmap
    int (*open)(struct inode *, struct file *);                     // open
    int (*release)(struct inode *, struct file *);                  // close
    int (*fsync)(struct file *, loff_t, loff_t, int);               // 同步
    // ...
};
```

**设计哲学：操作函数表是策略模式的内核实现——VFS 定义接口，具体 FS 提供实现。** 这是 C 语言版本的面向对象多态。

### 3.4 ext4 的 inode 与数据寻址

ext4 inode 的数据寻址使用 **Extent** 树：

```c
struct ext4_extent {
    __le32 ee_block;      // 起始逻辑块号
    __le16 ee_len;        // 长度（连续块数）
    __le16 ee_start_hi;   // 物理块号高位
    __le32 ee_start_lo;   // 物理块号低位
};
```

```
文件大小 100MB，块大小 4KB：

ext2（间接块）：
  inode → 12个直接块 → 1级间接 → 2级间接 → 3级间接
  12 × 4KB + 1024 × 4KB + ... → 需要多级间接寻址

ext4（Extent）：
  inode → Extent: [逻辑块0, 连续25600块, 物理块1000]
  → 一次寻址就找到了所有数据块！
```

**Extent 的设计哲学：用"范围"替代"逐块映射"——大多数文件的数据是连续的，用范围描述更高效。**

### 3.5 页缓存（Page Cache）

文件 I/O 不直接读写磁盘——通过**页缓存**：

```
read() 调用流程：
1. 检查页缓存中是否有请求的页
2. 如果有（缓存命中）→ 直接从内存返回数据
3. 如果没有（缓存未命中）→ 从磁盘读取到页缓存 → 返回数据

write() 调用流程：
1. 把数据写入页缓存
2. 标记页为 dirty
3. 异步写回磁盘（pdflush/kworker 线程）
```

```c
struct address_space {
    struct inode *host;              // 所属 inode
    struct xarray i_pages;           // 页缓存（页索引 → page）
    struct rb_root_cached i_mmap;    // 反向映射（mmap 的 VMA）
    const struct address_space_operations *a_ops; // 操作
    // ...
};

struct address_space_operations {
    int (*writepage)(struct page *page, struct writeback_control *wbc);
    int (*readpage)(struct file *, struct page *);
    int (*writepages)(struct address_space *, struct writeback_control *);
    int (*set_page_dirty)(struct page *);
    // ...
};
```

**页缓存的设计哲学：用内存作为磁盘的缓存——利用局部性原理，热数据在内存中，减少磁盘 I/O。**

---

## 四、Trade-offs：文件系统的关键权衡

### 4.1 日志策略

| 策略 | 日志内容 | 优点 | 缺点 |
|------|---------|------|------|
| Journal 模式 | 元数据 + 数据 | 最安全 | 性能最差（所有数据写两次） |
| Ordered 模式 | 只日志元数据，数据先写 | 安全且性能好（默认） | 数据可能旧但元数据一致 |
| Writeback 模式 | 只日志元数据 | 性能最好 | 断电后数据可能不一致 |

### 4.2 分配策略

| 策略 | 优点 | 缺点 |
|------|------|------|
| 立即分配 | 简单 | 碎片化、性能差 |
| 延迟分配 | 减少碎片、批量优化 | 内存需求大、延迟增加 |

**ext4 的选择**：延迟分配（delayed allocation）——写入时只写入页缓存，分配块时积累足够信息后批量分配，选择最优的物理块位置。

### 4.3 缓存 vs 直接 I/O

| 方案 | 优点 | 缺点 |
|------|------|------|
| 页缓存 | 自动缓存、预读优化 | 内存占用、数据可能不一致 |
| 直接 I/O (O_DIRECT) | 绕过缓存、低延迟 | 无缓存优化、需要应用自己管理 |

**数据库（如 PostgreSQL）通常使用 O_DIRECT**——因为数据库有自己的缓存层，不需要内核页缓存的额外开销。

---

## 五、Real-world Analysis：Linux 文件系统源码

### 5.1 open() 的完整调用链

```c
// fs/open.c（简化）
long do_sys_open(int dfd, const char __user *filename, int flags, umode_t mode)
{
    struct filename *tmp = getname(filename);  // 从用户空间拷贝文件名
    
    int fd = get_unused_fd_flags(flags);       // 分配文件描述符
    struct file *f = do_filp_open(dfd, tmp, &op); // 打开文件
    
    if (!IS_ERR(f)) {
        fsnotify_open(f);
        fd_install(fd, f);                     // 把 file 安装到 fd 表
    }
    
    return fd;
}
```

`do_filp_open` 的路径解析过程：

```c
// fs/namei.c（简化）
struct file *do_filp_open(int dfd, struct filename *pathname, ...)
{
    struct path path;
    
    // 路径解析：逐级查找 dentry
    int err = path_openat(dfd, pathname, &path, ...);
    
    // path 包含: path.dentry (目标 dentry) + path.mnt (挂载点)
    
    // 创建 file 对象
    struct file *file = alloc_empty_file(path.dentry->d_inode->i_mode);
    file->f_path = path;
    file->f_op = path.dentry->d_inode->i_fop;  // 从 inode 获取操作函数表
    
    // 调用文件系统的 open 方法
    if (file->f_op->open)
        file->f_op->open(path.dentry->d_inode, file);
    
    return file;
}
```

### 5.2 read() 的完整调用链

```c
// fs/read_write.c（简化）
ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
    if (file->f_op->read)
        return file->f_op->read(file, buf, count, pos);  // FS 自定义 read
    else
        return generic_file_read(file, buf, count, pos);  // VFS 通用 read
}

// mm/filemap.c（简化）
ssize_t generic_file_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
    struct address_space *mapping = file->f_mapping;
    
    // 1. 查页缓存
    struct page *page = pagecache_get_page(mapping, index, ...);
    
    if (page) {
        // 2. 缓存命中：直接从页缓存拷贝到用户缓冲区
        copy_page_to_iter(page, offset, count, &iter);
    } else {
        // 3. 缓存未命中：从磁盘读取到页缓存
        page = page_cache_sync_readahead(mapping, ...);
        copy_page_to_iter(page, offset, count, &iter);
    }
    
    return count;
}
```

### 5.3 dentry 缓存（DCache）

路径解析是昂贵的——每次 `open("/home/user/file")` 都要逐级查找。dentry 缓存保存最近解析的路径分量：

```c
// fs/dcache.c
struct dentry {
    struct qstr d_name;             // 名称
    struct inode *d_inode;          // inode
    struct dentry *d_parent;        // 父 dentry
    struct list_head d_subdirs;     // 子目录
    unsigned int d_flags;           // DCACHE_*
    spinlock_t d_lock;
    // ...
};
```

DCache 的设计：
- **哈希表**：快速查找 `(parent, name) → dentry`
- **LRU**：长期不用的 dentry 被回收
- **负 dentry**：缓存"不存在的路径"——避免重复查找失败的路径

**设计哲学：缓存路径解析结果——路径解析是 O(路径深度) 的操作，缓存后变成 O(1)。**

---

## 六、Hands-on Lab：lab05-vfs

### 实验1：Python 模拟 VFS 层次结构

```python
# src/simulators/vfs_sim.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class Inode:
    ino: int
    mode: int  # 文件类型和权限
    size: int = 0
    blocks: List[int] = field(default_factory=list)
    atime: float = 0
    mtime: float = 0
    is_dir: bool = False

@dataclass
class Dentry:
    name: str
    inode: Inode
    parent: Optional['Dentry'] = None
    children: Dict[str, 'Dentry'] = field(default_factory=dict)

class VirtualFileSystem:
    def __init__(self):
        self.inodes: Dict[int, Inode] = {}
        self.next_ino = 1
        self.root = self._create_dir("/")
    
    def _create_dir(self, name, parent=None):
        inode = Inode(ino=self.next_ino, mode=0o755, is_dir=True)
        self.inodes[inode.ino] = inode
        self.next_ino += 1
        dentry = Dentry(name=name, inode=inode, parent=parent)
        if parent:
            parent.children[name] = dentry
        return dentry
    
    def _create_file(self, name, parent):
        inode = Inode(ino=self.next_ino, mode=0o644)
        self.inodes[inode.ino] = inode
        self.next_ino += 1
        dentry = Dentry(name=name, inode=inode, parent=parent)
        parent.children[name] = dentry
        return dentry
    
    def _resolve_path(self, path):
        """路径解析：逐级查找 dentry"""
        if path == "/":
            return self.root
        
        parts = path.strip("/").split("/")
        current = self.root
        
        for part in parts:
            if part not in current.children:
                return None
            current = current.children[part]
        
        return current
    
    def mkdir(self, path):
        parent_path = "/".join(path.strip("/").split("/")[:-1])
        name = path.strip("/").split("/")[-1]
        
        parent = self._resolve_path(parent_path or "/")
        if not parent or not parent.inode.is_dir:
            return False
        if name in parent.children:
            return False
        
        self._create_dir(name, parent)
        return True
    
    def create(self, path):
        parent_path = "/".join(path.strip("/").split("/")[:-1])
        name = path.strip("/").split("/")[-1]
        
        parent = self._resolve_path(parent_path or "/")
        if not parent or not parent.inode.is_dir:
            return False
        if name in parent.children:
            return False
        
        self._create_file(name, parent)
        return True
    
    def ls(self, path):
        dentry = self._resolve_path(path)
        if not dentry or not dentry.inode.is_dir:
            return []
        return list(dentry.children.keys())
    
    def stat(self, path):
        dentry = self._resolve_path(path)
        if not dentry:
            return None
        return {
            "ino": dentry.inode.ino,
            "size": dentry.inode.size,
            "is_dir": dentry.inode.is_dir,
            "mode": oct(dentry.inode.mode),
        }

if __name__ == "__main__":
    vfs = VirtualFileSystem()
    
    vfs.mkdir("/home")
    vfs.mkdir("/home/user")
    vfs.create("/home/user/file.txt")
    vfs.mkdir("/home/user/docs")
    vfs.create("/home/user/docs/note.md")
    
    print("ls /:", vfs.ls("/"))
    print("ls /home/user:", vfs.ls("/home/user"))
    print("stat /home/user/file.txt:", vfs.stat("/home/user/file.txt"))
    print("stat /nonexistent:", vfs.stat("/nonexistent"))
```

### 实验2：C 实现简单 inode 文件系统

```c
// src/mini-kernel/mini_fs.c
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MAX_INODES 1024
#define MAX_BLOCKS 4096
#define BLOCK_SIZE 4096
#define MAX_NAME 32
#define MAX_DENTRIES 128

typedef enum { T_FILE, T_DIR } FileType;

typedef struct {
    int ino;
    FileType type;
    int size;
    int blocks[12];           // 直接块（简化版）
    int block_count;
    int link_count;           // 硬链接计数
} Inode;

typedef struct {
    char name[MAX_NAME];
    int ino;
} DirEntry;

typedef struct {
    Inode inodes[MAX_INODES];
    DirEntry dir_entries[MAX_INODES][MAX_DENTRIES];
    int dir_entry_count[MAX_INODES];
    char blocks[MAX_BLOCKS][BLOCK_SIZE];
    int next_ino;
    int next_block;
} FileSystem;

void fs_init(FileSystem *fs) {
    memset(fs, 0, sizeof(*fs));
    fs->next_ino = 1;
    fs->next_block = 0;
    
    // 创建根目录 (inode 0)
    fs->inodes[0].ino = 0;
    fs->inodes[0].type = T_DIR;
    fs->inodes[0].link_count = 1;
}

int fs_create(FileSystem *fs, const char *name, int parent_ino, FileType type) {
    if (fs->dir_entry_count[parent_ino] >= MAX_DENTRIES) return -1;
    
    int ino = fs->next_ino++;
    fs->inodes[ino].ino = ino;
    fs->inodes[ino].type = type;
    fs->inodes[ino].link_count = 1;
    
    // 在父目录中添加条目
    int idx = fs->dir_entry_count[parent_ino]++;
    strncpy(fs->dir_entries[parent_ino][idx].name, name, MAX_NAME);
    fs->dir_entries[parent_ino][idx].ino = ino;
    
    return ino;
}

void fs_ls(FileSystem *fs, int dir_ino) {
    printf("Directory (inode %d):\n", dir_ino);
    for (int i = 0; i < fs->dir_entry_count[dir_ino]; i++) {
        DirEntry *e = &fs->dir_entries[dir_ino][i];
        printf("  %s (inode %d, %s)\n",
               e->name, e->ino,
               fs->inodes[e->ino].type == T_DIR ? "dir" : "file");
    }
}

int fs_write(FileSystem *fs, int ino, const char *data, int len) {
    Inode *inode = &fs->inodes[ino];
    if (inode->type != T_FILE) return -1;
    
    int block = fs->next_block++;
    int offset = 0;
    int remaining = len;
    
    while (remaining > 0) {
        int chunk = remaining < BLOCK_SIZE ? remaining : BLOCK_SIZE;
        memcpy(fs->blocks[block + offset], data + offset * BLOCK_SIZE, chunk);
        inode->blocks[inode->block_count++] = block + offset;
        remaining -= chunk;
        offset++;
    }
    
    inode->size = len;
    return len;
}

int main() {
    FileSystem fs;
    fs_init(&fs);
    
    int home_ino = fs_create(&fs, "home", 0, T_DIR);
    int user_ino = fs_create(&fs, "user", home_ino, T_DIR);
    int file_ino = fs_create(&fs, "hello.txt", user_ino, T_FILE);
    
    fs_write(&fs, file_ino, "Hello, World!", 13);
    
    printf("=== Root ===\n");
    fs_ls(&fs, 0);
    printf("\n=== /home ===\n");
    fs_ls(&fs, home_ino);
    printf("\n=== /home/user ===\n");
    fs_ls(&fs, user_ino);
    
    printf("\nFile content (inode %d, size %d):\n", file_ino, fs.inodes[file_ino].size);
    printf("  %s\n", fs.blocks[fs.inodes[file_ino].blocks[0]]);
    
    return 0;
}
```

### 进阶实验

- 实现硬链接（多个 dentry 指向同一 inode）
- 实现简单的日志（写操作先记录日志再执行）
- 实现页缓存模拟（缓存文件数据页，统计命中率）
- 实现路径解析的 dentry 缓存

---

## 参考资源

- Linux 源码 `fs/` — VFS 和各文件系统实现
- Linux 源码 `include/linux/fs.h` — VFS 核心数据结构
- Linux 源码 `fs/ext4/` — ext4 实现
- *Understanding the Linux Kernel* Ch.12 — 文件系统
- *Linux Kernel Development* Ch.13 — VFS
- ext4 文档：https://ext4.wiki.kernel.org/