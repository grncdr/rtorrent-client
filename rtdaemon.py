import threading
from xmlrpclib import ServerProxy, Binary, ProtocolError
import time
class rTDaemon(threading.Thread):
    def __init__(self, queue, url):
        threading.Thread.__init__(self)
        self.connected = False
        self.setDaemon(True)
        self.jobs = queue
        self.open(url)

    def open(self, url):
        self.url = url
        self.connected = False
        self.proxy = ServerProxy(url)
        self.remote_request(('system.client_version', '', self._set_connected))

    def _set_connected(self, version):
        print "Connected to rtorrent version", version
        self.started = int(time.time())
        self.connected = True

    def run(self):
        while True:
            if not self.connected:
                self.open()
                time.sleep(5)
            else:
                job = self.jobs.get()
                if job[1] == 1 or int(time.time()) % job[0] == 0:
                    if self.remote_request(job[1:]): 
                        self.jobs.task_done()
                else:
                    self.jobs.put(job)


    def remote_request(self,job):
        if len(job) == 3:
            command, argument, callback = job
        elif len(job) == 2:
            callback = False
            command, argument = job

        try:
            response = getattr(self.proxy, command)(argument)
        except ProtocolError as e:
            print e.errcode, "-", e.url.split('@').pop(), '-', command
            self.jobs.put(job)
            return True

        if callback:
            callback(response)

        return True

    def send_file(self, filename, start=False):
        action = "load_raw"
        if start:
            action += "_start"
        torrent_file = open(filename,'rb')
        torrent_data = Binary(torrent_file.read()+torrent_file.read())
        torrent_file.close()
        self.jobs.put((1, action, torrent_data))

    def send_url(self, url, start=False):
        action = "load"
        if start:
            action += "_start"
        self.jobs.put((1, action, url))
