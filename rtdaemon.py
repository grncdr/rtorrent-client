import wx, threading
class RTDaemon(threading.Thread):
    def __init__(self, queue, proxy):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.queue = queue
        self.proxy = proxy

    def run(self):
        while True:
            job = self.queue.get()
            if self.remote_request(job): self.queue.task_done()

    def remote_request(self,job):
        param_list = ("command", "arguments", "callback_handler", "event")
        i = 0
        p = {}
        for param in job:
            if param:
                p[param_list[i]] = param
            i+=1
        try:
            response = getattr(self.proxy, p["command"])(p["arguments"])
        except:
            print "\n***Remote call failed***\nproxy:",self.proxy,"\ncall:",job[0],"(",job[1],")"
            self.queue.put(job)
            return True

        if "event" in p.keys() and "callback_handler" in p.keys():
            p["event"].response = response
            wx.PostEvent(p["callback_handler"], p["event"])
        return True
