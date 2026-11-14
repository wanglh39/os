"""
页面置换算法模拟器
对比 FIFO、LRU、Clock 三种页面置换算法的命中率。
"""
from collections import deque, OrderedDict


def fifo_replacement(access_sequence, num_frames):
    frames = deque()
    page_set = set()
    hits = 0
    misses = 0
    trace = []

    for page in access_sequence:
        if page in page_set:
            hits += 1
            trace.append(f"  Page {page}: HIT")
        else:
            misses += 1
            if len(frames) >= num_frames:
                evicted = frames.popleft()
                page_set.remove(evicted)
                trace.append(f"  Page {page}: MISS (evicted {evicted})")
            else:
                trace.append(f"  Page {page}: MISS")
            frames.append(page)
            page_set.add(page)

    return hits, misses, trace


def lru_replacement(access_sequence, num_frames):
    cache = OrderedDict()
    hits = 0
    misses = 0
    trace = []

    for page in access_sequence:
        if page in cache:
            hits += 1
            cache.move_to_end(page)
            trace.append(f"  Page {page}: HIT")
        else:
            misses += 1
            if len(cache) >= num_frames:
                evicted, _ = cache.popitem(last=False)
                trace.append(f"  Page {page}: MISS (evicted {evicted})")
            else:
                trace.append(f"  Page {page}: MISS")
            cache[page] = True

    return hits, misses, trace


def clock_replacement(access_sequence, num_frames):
    frames = [None] * num_frames
    referenced = [False] * num_frames
    pointer = 0
    hits = 0
    misses = 0
    trace = []

    for page in access_sequence:
        if page in frames:
            hits += 1
            referenced[frames.index(page)] = True
            trace.append(f"  Page {page}: HIT")
        else:
            misses += 1
            while referenced[pointer]:
                referenced[pointer] = False
                pointer = (pointer + 1) % num_frames
            evicted = frames[pointer]
            frames[pointer] = page
            referenced[pointer] = True
            if evicted is not None:
                trace.append(f"  Page {page}: MISS (evicted {evicted})")
            else:
                trace.append(f"  Page {page}: MISS")
            pointer = (pointer + 1) % num_frames

    return hits, misses, trace


def run_all(seq, frames):
    print(f"Access sequence: {seq}")
    print(f"Frames: {frames}\n")

    for name, func in [("FIFO", fifo_replacement),
                        ("LRU", lru_replacement),
                        ("Clock", clock_replacement)]:
        h, m, trace = func(seq, frames)
        rate = h / (h + m) * 100
        print(f"=== {name} ===")
        for line in trace[:10]:
            print(line)
        if len(trace) > 10:
            print(f"  ... ({len(trace) - 10} more)")
        print(f"Hits={h}, Misses={m}, Hit rate={rate:.1f}%\n")


if __name__ == "__main__":
    seq = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
    run_all(seq, frames=3)

    print("=" * 50)
    print("Belady anomaly test (FIFO with 3 vs 4 frames):")
    seq2 = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
    h3, m3, _ = fifo_replacement(seq2, 3)
    h4, m4, _ = fifo_replacement(seq2, 4)
    print(f"  3 frames: hits={h3}, misses={m3}")
    print(f"  4 frames: hits={h4}, misses={m4}")
    print(f"  More frames but more misses? {m4 > m3}")