from __future__ import with_statement
import threading

class MultiQueue(object):
    def __init__(self):
        self.lock = threading.Lock()
        self._lists = {}
        self.clear()

    def __len__(self):
        with self.lock:
            #print "Locked multi-queue"
            length = len(self._lists)
        #print "Released multi-queue"
        return length

    def __getitem__(self, i):
        return self.get(i)

    def keys(self):
        with self.lock:
            #print "Locked multi-queue"
            keys = self._lists.keys()
        #print "Released multi-queue"
        return keys

    def put(self, i, job):
        with self.lock:
            #print "Locked multi-queue"
            if i not in self._lists:
                self._lists[i] = [job]
            else:
                self._lists[i].append(job)

    def get(self, i, clear=False):
        with self.lock:
            #print "Locked multi-queue"
            if i not in self._lists:
                rv = []
            else:
                rv = list(self._lists[i])
                if clear:
                    del(self._lists[i])
        #print "Released multi-queue"
        return rv

    def remove(self, test):
        with self.lock:
            #print "Locked multi-queue"
            for list in self._lists.values():
                for item in list:
                    if test(item):
                        list.remove(item)

    def move(self, job, new_f):
        rv = False
        with self.lock:
            #print "Locked multi-queue"
            for list in self.jobs:
                for (i, cjob) in zip(range(len(list)), list):
                    if job[0:2] == cjob[0:2]:
                        self.jobs[new_f].append(list.pop(i))
                        rv = not rv
        #print "Released multi-queue"
        return rv

    def clear(self):
        with self.lock:
            #print "Locked multi-queue"
            del(self._lists)
            self._lists = {}
        #print "Released multi-queue"
