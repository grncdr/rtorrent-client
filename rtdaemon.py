import threading
from xmlrpclib import ServerProxy, Binary, ProtocolError
import time

def make_hash(tdata):
    from bencode import bdecode, bencode
    from hashlib import sha1
    return sha1(bencode(bdecode(tdata)['info'])).hexdigest().upper()

class rTDaemon(threading.Thread):
    def __init__(self, queue, url):
        threading.Thread.__init__(self)
        self.connected = False
        self.setDaemon(True)
        self.jobs = queue
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

    def send_torrent(self, source, dest, start, url=False):
        if url:
            import urllib2
            torrent_file = urllib2.urlopen(source)
        else:
            torrent_file = open(source,'rb')
        torrent_data = torrent_file.read()
        torrent_file.close()
        infohash = make_hash(torrent_data)
        torrent_data = Binary(torrent_data)
        def dest_callback(rv):
            print 'Hit dest_callback', infohash, dest, start
            def start_callback(rv):
                print 'Hit start_callback', infohash, dest, start
                if start:
                    time.sleep(3)
                    self.jobs.append(('d.start', infohash))
            time.sleep(3)
            print 'adding job to queue'
            self.jobs.append(('d.set_directory', (infohash, dest), 
                               start_callback))
        self.jobs.appendleft(('load_raw', torrent_data, dest_callback))

