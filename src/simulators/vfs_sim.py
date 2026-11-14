"""
VFS 层次结构模拟器
模拟 inode、dentry、路径解析等 VFS 核心概念。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Inode:
    ino: int
    mode: int = 0o644
    size: int = 0
    is_dir: bool = False
    link_count: int = 1


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
        parts = path.strip("/").split("/")
        name = parts[-1]
        parent_path = "/".join(parts[:-1])
        parent = self._resolve_path(parent_path or "/")
        if not parent or not parent.inode.is_dir or name in parent.children:
            return False
        self._create_dir(name, parent)
        return True

    def create(self, path):
        parts = path.strip("/").split("/")
        name = parts[-1]
        parent_path = "/".join(parts[:-1])
        parent = self._resolve_path(parent_path or "/")
        if not parent or not parent.inode.is_dir or name in parent.children:
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
            "link_count": dentry.inode.link_count,
        }

    def hardlink(self, src_path, dst_path):
        """创建硬链接：多个 dentry 指向同一 inode"""
        src = self._resolve_path(src_path)
        if not src or src.inode.is_dir:
            return False
        parts = dst_path.strip("/").split("/")
        name = parts[-1]
        parent_path = "/".join(parts[:-1])
        parent = self._resolve_path(parent_path or "/")
        if not parent or name in parent.children:
            return False
        new_dentry = Dentry(name=name, inode=src.inode, parent=parent)
        parent.children[name] = new_dentry
        src.inode.link_count += 1
        return True


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

    vfs.hardlink("/home/user/file.txt", "/home/user/docs/link_to_file")
    print("\nAfter hardlink:")
    print("ls /home/user/docs:", vfs.ls("/home/user/docs"))
    print("stat /home/user/file.txt:", vfs.stat("/home/user/file.txt"))
    print("stat /home/user/docs/link_to_file:", vfs.stat("/home/user/docs/link_to_file"))
    print("  → Same inode number, link_count=2")