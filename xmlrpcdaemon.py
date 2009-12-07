import threading
from xmlrpclib import ServerProxy, Binary, ProtocolError
import time
from collections import deque

class XMLRPCDaemon(threading.Thread):
    def __init__(self, queue, url):
        threading.Thread.__init__(self)
        self.connected = False
        self.setDaemon(True)
        self.jobs = deque()
        self.proceed = True
        self.open(url)

    def open(self, url):
        self.url = url
        self.connected = False
        self.proxy = ServerProxy(url)
        self.remote_request(('system.client_version', '', self._set_connected))

    def _set_connected(self, version):
        self.started = int(time.time())
        self.connected = True

    def run(self):
        while self.proceed:
            if not self.connected:
                self.open(self.url)
                time.sleep(5)
            else:
                try:
                    job = self.jobs.popleft()
                except IndexError:
                    time.sleep(1)
                    continue
                if not self.remote_request(job): 
                    self.jobs.append(job)

    def remote_request(self,job):
        if len(job) == 3:
            command, argument, callback = job
        elif len(job) == 2:
            callback = False
            command, argument = job
        try:
            if command == 'd.set_directory':
                print 'Setting directory:', argument
            if type(argument) == tuple:
                response = getattr(self.proxy, command)(*argument)
            else:
                response = getattr(self.proxy, command)(argument)
        except ProtocolError, e:
            print e.errcode, "-", e.url.split('@').pop(), '-', command
            return False
        except:
            return False
        if callback:
            callback(response)
        return True
