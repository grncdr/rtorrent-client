import threading

class MultiQueue:
    lock = threading.Lock()
    def __init__(self):
        self.lock.acquire()
        self.queue = {}
        self.lock.release()
    def __len__(self):
        self.lock.acquire()
        size = len(self.queue)
        self.lock.release()
        return size
    def __contains__(self, k):
        if k in self.queue.keys():
            return True
        return False
    def inc(self, k):
        self.changecount(k, 1)
    def dec(self, k):
        self.changecount(k, -1)
    def changecount(self, k, howmuch=0):
        self.lock.acquire()
        if k not in self.queue.keys():
            self.queue[k] = howmuch
        else:
            self.queue[k] += howmuch
            if self.queue[k] < 1: del self.queue[k]
        self.lock.release()

