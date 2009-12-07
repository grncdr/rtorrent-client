import threading
from collections import deque

class MultiQueue(object):

    def __init__(self):
        self.lock = threading.Lock()
        self._lists = {}
        self.clear()

    def __len__(self):
        self.lock.acquire()
        length = len(self._lists)
        self.lock.release()
        return length

    def __getitem__(self, i):
        return self.get(i)

    def keys(self):
        self.lock.acquire()
        keys = self._lists.keys()
        self.lock.release()
        return keys

    def put(self, l, job):
        self.lock.acquire()
        if l not in self._lists:
            self._lists[l] = [job]
        else:
            self._lists[l].append(job)
        self.lock.release()

    def get(self, l, clear=False):
        self.lock.acquire()
        if l not in self._lists:
            list = []
        else:
            list = self._lists[l]
            if clear:
                del(self._lists[l])
        self.lock.release()
        return list

    def remove(self, test):
        self.lock.acquire()
        for list in self._lists.values():
            for item in list:
                if test(item):
                    list.remove(item)
        self.lock.release()

    def move(self, job, new_f):
        for list in self.jobs:
            for (i, cjob) in zip(range(len(list)), list):
                if job[0:2] == cjob[0:2]:
                    self.jobs[new_f].append(list.pop(i))
                    return True
        return False

    def clear(self):
        self.lock.acquire()
        del(self._lists)
        self._lists = {}
        self.lock.release()
