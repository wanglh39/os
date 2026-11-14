"""
Buddy System 可视化模拟器
模拟伙伴系统的分配、分裂和合并过程。
"""


class BuddySystem:
    def __init__(self, max_order=6):
        self.max_order = max_order
        self.total_pages = 1 << max_order
        self.free_lists = {i: [] for i in range(max_order + 1)}
        self.free_lists[max_order] = [0]
        self.allocated = {}

    def alloc(self, order):
        for o in range(order, self.max_order + 1):
            if self.free_lists[o]:
                block = self.free_lists[o].pop(0)
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
            found = False
            for i, b in enumerate(self.free_lists[order]):
                if b == buddy:
                    self.free_lists[order].pop(i)
                    found = True
                    break
            if not found:
                break
            block = min(block, buddy)
            order += 1
        self.free_lists[order].append(block)

    def visualize(self):
        for o in range(self.max_order + 1):
            if self.free_lists[o]:
                size = 1 << o
                print(f"  Order {o} ({size:4d} pages): {self.free_lists[o]}")
        if self.allocated:
            print(f"  Allocated: {dict(sorted(self.allocated.items()))}")


if __name__ == "__main__":
    bs = BuddySystem(max_order=6)
    print("=== Initial state ===")
    bs.visualize()

    a = bs.alloc(2)
    print(f"\n=== After alloc order 2 at page {a} ===")
    bs.visualize()

    b = bs.alloc(3)
    print(f"\n=== After alloc order 3 at page {b} ===")
    bs.visualize()

    c = bs.alloc(1)
    print(f"\n=== After alloc order 1 at page {c} ===")
    bs.visualize()

    bs.free(a)
    print(f"\n=== After free page {a} ===")
    bs.visualize()

    bs.free(c)
    print(f"\n=== After free page {c} ===")
    bs.visualize()

    bs.free(b)
    print(f"\n=== After free page {b} (should merge back to order 6) ===")
    bs.visualize()