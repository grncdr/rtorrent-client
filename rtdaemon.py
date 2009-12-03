import threading
from xmlrpclib import ServerProxy, Binary
class rTDaemon(threading.Thread):
    def __init__(self, queue=None, url=None):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.queue = queue
        self.open(url)

    def open(self, url):
        self.proxy = ServerProxy(url)

    def run(self):
        while True:
            job = self.queue.get()
            if self.remote_request(job): self.queue.task_done()

    def remote_request(self,job):
        param_list = ("command", "argument", "callback")
        i = 0
        p = {}
        for param in job:
            if param:
                p[param_list[i]] = param
            i+=1

        try:
            response = getattr(self.proxy, p["command"])(p["argument"])
        except:
            #print "\n***Remote call failed***\nproxy:",self.proxy,"\ncall:",job[0], job[1]
            self.queue.put(job)
            return True

        if "callback" in p.keys():
            p["callback"](response)

        return True

    def send_file(self, filename, start=False):
        action = "load_raw"
        if start:
            action += "_start"
        torrent_file = open(filename,'rb')
        torrent_data = Binary(torrent_file.read()+torrent_file.read())
        torrent_file.close()
        self.queue.put((action, torrent_data))

    def send_url(self, url, start=False):
        action = "load"
        if start:
            action += "_start"
        self.queue.put((action, url))
