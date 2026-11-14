/*
 * 简单 inode 文件系统
 * 模拟 inode、目录条目、文件创建和读写。
 *
 * 编译: gcc mini_fs.c -o mini_fs && ./mini_fs
 */
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
    int blocks[12];
    int block_count;
    int link_count;
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

static void fs_init(FileSystem *fs) {
    memset(fs, 0, sizeof(*fs));
    fs->next_ino = 1;
    fs->next_block = 0;
    fs->inodes[0].ino = 0;
    fs->inodes[0].type = T_DIR;
    fs->inodes[0].link_count = 1;
}

static int fs_create(FileSystem *fs, const char *name, int parent_ino, FileType type) {
    if (fs->dir_entry_count[parent_ino] >= MAX_DENTRIES) return -1;

    int ino = fs->next_ino++;
    fs->inodes[ino].ino = ino;
    fs->inodes[ino].type = type;
    fs->inodes[ino].link_count = 1;

    int idx = fs->dir_entry_count[parent_ino]++;
    strncpy(fs->dir_entries[parent_ino][idx].name, name, MAX_NAME);
    fs->dir_entries[parent_ino][idx].ino = ino;

    return ino;
}

static void fs_ls(FileSystem *fs, int dir_ino) {
    printf("Directory (inode %d):\n", dir_ino);
    for (int i = 0; i < fs->dir_entry_count[dir_ino]; i++) {
        DirEntry *e = &fs->dir_entries[dir_ino][i];
        printf("  %s (inode %d, %s)\n",
               e->name, e->ino,
               fs->inodes[e->ino].type == T_DIR ? "dir" : "file");
    }
}

static int fs_write(FileSystem *fs, int ino, const char *data, int len) {
    Inode *inode = &fs->inodes[ino];
    if (inode->type != T_FILE) return -1;

    int block = fs->next_block++;
    memcpy(fs->blocks[block], data, len < BLOCK_SIZE ? len : BLOCK_SIZE);
    inode->blocks[inode->block_count++] = block;
    inode->size = len;
    return len;
}

int main(void) {
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
    fflush(stdout);

    return 0;
}