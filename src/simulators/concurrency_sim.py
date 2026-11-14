"""
并发问题模拟器
演示竞态条件、锁的正确使用、死锁和哲学家就餐问题。
"""
import threading
import time


class BankAccount:
    def __init__(self, balance=1000):
        self.balance = balance

    def unsafe_deposit(self, amount):
        temp = self.balance
        time.sleep(0.0001)
        self.balance = temp + amount

    def unsafe_withdraw(self, amount):
        temp = self.balance
        time.sleep(0.0001)
        self.balance = temp - amount

    def safe_deposit(self, amount, lock):
        with lock:
            self.balance += amount

    def safe_withdraw(self, amount, lock):
        with lock:
            self.balance -= amount


def test_unsafe():
    account = BankAccount(1000)
    threads = []
    for _ in range(100):
        threads.append(threading.Thread(target=account.unsafe_deposit, args=(10,)))
    for _ in range(100):
        threads.append(threading.Thread(target=account.unsafe_withdraw, args=(10,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Unsafe: balance = {account.balance} (expected 1000)")


def test_safe():
    account = BankAccount(1000)
    lock = threading.Lock()
    threads = []
    for _ in range(100):
        threads.append(threading.Thread(target=account.safe_deposit, args=(10, lock)))
    for _ in range(100):
        threads.append(threading.Thread(target=account.safe_withdraw, args=(10, lock)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Safe:   balance = {account.balance} (expected 1000)")


class Philosopher:
    def __init__(self, name, left_fork, right_fork):
        self.name = name
        self.left_fork = left_fork
        self.right_fork = right_fork

    def dine(self):
        for _ in range(3):
            time.sleep(0.05)
            self.left_fork.acquire()
            if not self.right_fork.acquire(timeout=0.5):
                self.left_fork.release()
                continue
            time.sleep(0.05)
            self.right_fork.release()
            self.left_fork.release()


def test_philosophers_deadlock_free():
    """不会死锁的版本：最后一个哲学家先拿右叉子"""
    forks = [threading.Lock() for _ in range(5)]
    philosophers = []
    for i in range(5):
        left = forks[i]
        right = forks[(i + 1) % 5]
        if i == 4:
            philosophers.append(Philosopher(f"P{i}", right, left))
        else:
            philosophers.append(Philosopher(f"P{i}", left, right))

    threads = [threading.Thread(target=p.dine) for p in philosophers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    alive = [t for t in threads if t.is_alive()]
    print(f"Philosophers: {'deadlock!' if alive else 'all done'}")


if __name__ == "__main__":
    print("=== Race condition test ===")
    test_unsafe()
    test_safe()

    print("\n=== Dining philosophers ===")
    test_philosophers_deadlock_free()