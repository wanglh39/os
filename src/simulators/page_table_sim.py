"""
多级页表翻译模拟器
模拟 x86-64 四级页表的地址翻译过程，包括权限检查和缺页异常。
"""


class PageTableEntry:
    def __init__(self):
        self.frame = None
        self.present = False
        self.readable = True
        self.writable = True
        self.executable = True
        self.user = True
        self.accessed = False
        self.dirty = False


class MultiLevelPageTable:
    """模拟 x86-64 四级页表"""

    def __init__(self, levels=4, bits_per_level=9, page_offset_bits=12):
        self.levels = levels
        self.bits_per_level = bits_per_level
        self.page_offset_bits = page_offset_bits
        self.root = {}
        self.physical_memory = {}
        self.tlb = {}  # TLB 缓存
        self.tlb_hits = 0
        self.tlb_misses = 0
        self.page_faults = 0

    def _extract_indices(self, vaddr):
        offset = vaddr & ((1 << self.page_offset_bits) - 1)
        vaddr >>= self.page_offset_bits
        indices = []
        for _ in range(self.levels):
            indices.append(vaddr & ((1 << self.bits_per_level) - 1))
            vaddr >>= self.bits_per_level
        indices.reverse()
        return indices, offset

    def _tlb_key(self, vaddr):
        return vaddr >> self.page_offset_bits

    def map(self, vaddr, frame, flags=None):
        indices, _ = self._extract_indices(vaddr)
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
        # 1. 先查 TLB
        tlb_key = self._tlb_key(vaddr)
        offset = vaddr & ((1 << self.page_offset_bits) - 1)
        if tlb_key in self.tlb:
            self.tlb_hits += 1
            entry = self.tlb[tlb_key]
        else:
            self.tlb_misses += 1
            # 2. 走多级页表
            indices, _ = self._extract_indices(vaddr)
            node = self.root
            for i in range(self.levels - 1):
                if indices[i] not in node:
                    self.page_faults += 1
                    return None, "Page table not found (level {})".format(i)
                node = node[indices[i]]

            if indices[-1] not in node:
                self.page_faults += 1
                return None, "PTE not found"

            entry = node[indices[-1]]
            # 更新 TLB
            self.tlb[tlb_key] = entry

        # 3. 检查 present 位
        if not entry.present:
            self.page_faults += 1
            return None, "Page not present (Page Fault!)"

        # 4. 权限检查
        if access_type == 'write' and not entry.writable:
            return None, "Write protection fault (COW?)"
        if access_type == 'execute' and not entry.executable:
            return None, "Execute protection fault (NX)"

        # 5. 更新 A/D 位
        entry.accessed = True
        if access_type == 'write':
            entry.dirty = True

        phys_addr = (entry.frame << self.page_offset_bits) | offset
        return phys_addr, "OK"

    def flush_tlb(self):
        self.tlb.clear()

    def stats(self):
        total = self.tlb_hits + self.tlb_misses
        hit_rate = self.tlb_hits / total * 100 if total > 0 else 0
        return {
            "tlb_hits": self.tlb_hits,
            "tlb_misses": self.tlb_misses,
            "tlb_hit_rate": f"{hit_rate:.1f}%",
            "page_faults": self.page_faults,
        }


if __name__ == "__main__":
    pt = MultiLevelPageTable()

    pt.map(0x1000, 0x500, {'writable': False})
    pt.map(0x2000, 0x800, {'executable': False})
    pt.map(0x3000, 0xA00)
    pt.map(0x10000, 0xB00)

    tests = [
        (0x1000, 'read', "Read COW page"),
        (0x1000, 'write', "Write COW page (should fail)"),
        (0x2000, 'execute', "Execute NX page (should fail)"),
        (0x3000, 'write', "Write normal page"),
        (0x4000, 'read', "Read unmapped page (should fault)"),
        (0x1000, 'read', "Read COW page again (TLB hit)"),
    ]

    for vaddr, access, desc in tests:
        phys, status = pt.translate(vaddr, access)
        print(f"{desc}: vaddr=0x{vaddr:X} → phys={phys}, status={status}")

    print(f"\nStats: {pt.stats()}")