from __future__ import with_statement
import socket
import threading
import xmlrpclib 
import socket # For exception handling
import time
import Queue

class XMLRPCDaemon(threading.Thread):
    def __init__(self, url):
        threading.Thread.__init__(self)
        self.connected = False
        #self.setDaemon(True)
        self.jobs = Queue.Queue()
        self.proceed = True
        self.url = url

    def open(self, url):
        self.url = url
        self.connected = False
        self.proxy = xmlrpclib.ServerProxy(url)
        self._remote_request(('system.client_version', '', self._set_connected))

    def _set_connected(self, version):
        self.connected = True

    def clear(self):
        with self.jobs.mutex:
            self.jobs.queue.clear()

    def put(self, job):
        self.jobs.put(job)

    def put_first(self, job):
        with self.jobs.mutex:
            self.jobs.queue.appendleft(job)

    def run(self):
        while self.proceed:
            if self.connected:
                try:
                    job = self.jobs.get(True, 1)
                except Queue.Empty:
                    continue
                if self._remote_request(job): 
                    self.jobs.put(job)
                else:
                    self.jobs.task_done()
            else:
                self.open(self.url)

    def _remote_request(self,job):
        if len(job) == 3:
            command, argument, callback = job
        elif len(job) == 2:
            callback = False
            command, argument = job
        else:
            raise TypeError("Jobs must be of length 2 or 3")
        try:
            if type(argument) == tuple:
                response = getattr(self.proxy, command)(*argument)
            else:
                response = getattr(self.proxy, command)(argument)
        except xmlrpclib.ProtocolError, e:
            print e.errcode, "-", e.url.split('@').pop(), '-', command
            return False
        except socket.gaierror, e:
            self._connected = False
            print e
            return False
        except socket.error, e:
            self._connected = False
            print e
            time.sleep(10)
            return False

        if callback:
            callback(response)

        return True
