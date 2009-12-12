from __future__ import with_statement
import threading

class MultiQueue(object):
    def __init__(self):
        self.lock = threading.Lock()
        self._lists = {}
        self.clear()

    def __len__(self):
        with self.lock:
            return len(self._lists)

    def __getitem__(self, i):
        return self.get(i)

    def keys(self):
        with self.lock:
            keys = self._lists.keys()
            return keys

    def put(self, i, job):
        with self.lock:
            if i not in self._lists:
                self._lists[i] = [job]
            else:
                self._lists[i].append(job)

    def get(self, i, clear=False):
        with self.lock:
            if i not in self._lists:
                return []
            else:
                rv = list(self._lists[i])
                if clear:
                    del(self._lists[i])
                return rv

    def remove(self, test):
        with self.lock:
            for l in self._lists.values():
                for item in l:
                    if test(item):
                        l.remove(item)

    def move(self, job, new_f):
        with self.lock:
            for l in self._lists.values():
                for (i, cjob) in zip(range(len(l)), l):
                    if i == new_f:
                        continue
                    if job == cjob:
                        self.jobs[new_f].append(l.pop(i))
                        return True
        return False

    def clear(self):
        with self.lock:
            del(self._lists)
            self._lists = {}
