from __future__ import with_statement
import threading
import xmlrpclib 
import socket # For exception handling
import time
from Queue import Queue

class XMLRPCDaemon(threading.Thread):
    def __init__(self, url):
        threading.Thread.__init__(self)
        self.connected = False
        self.setDaemon(True)
        self.jobs = Queue()
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
        return None # Stub

    def put(self, job):
        self.jobs.put(job)

    def put_first(self, job):
        with self.jobs.mutex:
            self.jobs.queue.appendleft(job)

    def run(self):
        while self.proceed:
            if not self.connected:
                self.open(self.url)
            else:
                try:
                    job = self.jobs.get()
                except IndexError:
                    time.sleep(1)
                    continue
                if not self._remote_request(job): 
                    self.jobs.put(job)

    def _remote_request(self,job):
        if len(job) == 3:
            command, argument, callback = job
        elif len(job) == 2:
            callback = False
            command, argument = job
        try:
            if type(argument) == tuple:
                response = getattr(self.proxy, command)(*argument)
            else:
                response = getattr(self.proxy, command)(argument)
        except xmlrpclib.ProtocolError, e:
            print e.errcode, "-", e.url.split('@').pop(), '-', command
            return False
        except socket.gaierror:
            self._connected = False
            return False
        #except xmlrpclib.error:
        #    print error
        #    return False

        if callback:
            callback(response)
        return True
