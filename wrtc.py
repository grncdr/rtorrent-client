#!/usr/bin/python -d

'''
File: wrTc.py
Author: Stephen Sugden (grncdr)
Description: This is a little app that connects to and monitors a remote 
             rTorrent via xmlrpc. It can also upload local torrent files to a 
             remote machine
'''

from __future__ import with_statement
import os, sys, threading, wx, time, math
from ObjectListView import ObjectListView, ColumnDefn
from settings_manager import SettingsManager
import xmlrpcdaemon 
from xmlrpclib import Binary
from multiqueue import MultiQueue

APP_NAME = 'wrTc'
WRTC_OSX = hasattr(os, 'uname') and (os.uname()[0] == 'Darwin')
VIEW_LIST = ["incomplete", "seeding", "stopped"]
MAX_REFRESH_CYCLE = 30

def format_bytes(bytes):
    ''' prettifies sizes given in bytes '''
    units = ("B", "KB", "MB", "GB", "TB")
    bytes = float(bytes)
    for unit in units:
        if abs(bytes) < 1024:
            break
        bytes /= 1024
    return str(round(bytes,2))+unit

def make_hash(tdata):
    ''' Create an infohash for the given torrent data '''
    from bencode import bdecode, bencode
    from hashlib import sha1
    return sha1(bencode(bdecode(tdata)['info'])).hexdigest().upper()

class wrtcApp(wx.App):
    def __init__(self, *args, **kwargs):
        def settings_save_callback(*args, **kwargs):
            self.rtorrent.open(self.settings_manager.get("DEFAULT",'rTorrent URL'))

        self.settings_manager = SettingsManager(APP_NAME+'.cfg', {
            'rtorrent url': 'http://localhost/RPC2', 
            'remote root': '/'
        }, settings_save_callback)

        self.rtorrent = xmlrpcdaemon.XMLRPCDaemon( # Can't shorten this one!
            self.settings_manager.get("rTorrent URL"))
        self.rtorrent.start()
        wx.App.__init__(self, *args, **kwargs)
        self.updater = UpdateScheduler(self)
        self.updater.start()
        self.Bind(wx.EVT_ACTIVATE_APP, self.activate)

    def OnInit(self):
        self.frame = MainWindow(None, wx.ID_ANY, 
                                APP_NAME+" - wxPython rTorrent client") 
        self.frame.Show()
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.load_torrent(filename=sys.argv[1])
        return True

    def raise_frame(self):
        try: self.frame.Raise()
        except: pass

    def activate(self, evt):
        if evt.GetActive():
            self.raise_frame()
        evt.Skip()

    def MacOpenFile(self, filename):
        self.load_torrent(filename=filename)

    def MacReopenApp(self, *args, **kwargs):
        self.raise_frame()
        
    def load_torrent(self,e=None,filename=None):
        dlg = LoadTorrentDialog(self.settings_manager.get('remote root'))
        if filename:
            dlg.filepath.SetValue(filename)
        if dlg.ShowModal() == wx.ID_OK:
            self.send_torrent(dlg)
        dlg.Destroy()

    def send_torrent(self, dlg):
        start = dlg.start_immediate.GetValue()
        dest = dlg.browser.GetPyData(dlg.browser.GetSelection())['path']
        if dlg.filepath.GetValue() != '':
            torrent_file = open(dlg.filepath.GetValue(),'rb')
        elif dlg.url.GetValue() != '':
            import urllib2
            torrent_file = urllib2.urlopen(dlg.url.GetValue())
        torrent_data = torrent_file.read()
        torrent_file.close()
        infohash = make_hash(torrent_data)
        torrent_data = Binary(torrent_data)
        def dest_callback(rv):
            def start_callback(rv):
                if start:
                    self.rtorrent.put(('d.start', infohash))
            self.rtorrent.put(('d.set_directory', (infohash, dest), 
                               start_callback))
        self.rtorrent.put(('load_raw', torrent_data, dest_callback))

class MainWindow(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))

        self.menu_bar = wx.MenuBar()

        self.file_menu = wx.Menu()
        self.file_menu.Append(wx.ID_OPEN, "Add &Torrent")
        self.Bind(wx.EVT_MENU, wx.GetApp().load_torrent, id=wx.ID_OPEN)
        self.file_menu.Append(wx.ID_PREFERENCES, "&Preferences")
        self.Bind(wx.EVT_MENU, wx.GetApp().settings_manager.show_dialog, 
                  id=wx.ID_PREFERENCES)
        self.file_menu.Append(wx.ID_EXIT, "&Quit")
        self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
        self.menu_bar.Append(self.file_menu, "&File")

        self.help_menu = wx.Menu()
        self.help_menu.Append(wx.ID_ABOUT, "&About "+APP_NAME)
        self.Bind(wx.EVT_MENU, self.on_about_request, id=wx.ID_ABOUT)
        self.menu_bar.Append(self.help_menu, "&Help")

        self.SetMenuBar(self.menu_bar)

        self.notebook = rTorrentNotebook(self, VIEW_LIST)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(main_sizer)
        self.Bind(wx.EVT_CLOSE, self.on_exit)
#    Icons = {}
#    Icons['play'] = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR)
#    Icons['pause'] = wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_TOOLBAR)
#    Icons['add'] = wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR)
#    Icons['remove'] = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_FRAME_ICON)
#    ControlIcons = (Icons['play'], Icons['pause'])

    def on_about_request(self, evt):
        dlg = wx.MessageDialog(self, "wxPython rTorrent client", APP_NAME, 
                               wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()

    def on_exit(self,e):
        wx.GetApp().updater.proceed = False
        wx.GetApp().rtorrent.proceed = False
        self.Show(False)
        wx.GetApp().updater.join()
        wx.GetApp().rtorrent.join()
        self.Destroy()


class rTorrentNotebook(wx.Notebook):
    def __init__(self, parent, views, *args, **kwargs):
        wx.Notebook.__init__(self, parent, *args, **kwargs)
        self.load_views(views)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.page_changed)

    def load_views(self, views):
        for view in views:
            self.AddPage(rTorrentView(self, view), view.capitalize());
        self.GetCurrentPage().get_list()

    def page_changed(self, evt):
        self.GetPage(evt.GetSelection()).get_list()
        evt.Skip()

class rTorrentView(wx.NotebookPage):
    _columns = [
        ColumnDefn("Name", valueGetter="name", isSpaceFilling=True, 
                   minimumWidth=100, maximumWidth=300),
        ColumnDefn("Up", "right", 70, "up_rate", stringConverter=format_bytes),
        ColumnDefn("Down", "right", 70, "down_rate", 
                   stringConverter=format_bytes),
        ColumnDefn("Size", "right", 70, "size_bytes", 
                   stringConverter=format_bytes),
        ColumnDefn("Up Total", "right", 80, "up_total", 
                   stringConverter=format_bytes),
        ColumnDefn("Down Total", "right", 80, "bytes_done", 
                   stringConverter=format_bytes),
        ColumnDefn("Ratio", "right", fixedWidth=40, valueGetter="ratio", 
                   stringConverter="%s%%"),
        #ColumnDefn("S", "center", 25, "peers_complete"),
        #ColumnDefn("P", "center", 25, "peers_accounted"),
    ]
    def __init__(self, parent, title="default"):
        self.title = title
        self.torrents = []
        self.joblist = MultiQueue()
        wx.NotebookPage.__init__(self, parent)

        self.olv = ObjectListView(self, style=wx.LC_REPORT)
        self.olv.SetEmptyListMsg("No torrents")
        self.olv.SetColumns(self._columns)
        self.joblist.put(5, ("download_list", self.title, self.set_list))

    def __repr__(self):
        return "<rTorrentView '%s'>" % self.title.capitalize()

    def get_list(self):
        ''' Clear the queue and update the current page. 
        Called on page change '''
        self.joblist.put(0, ("download_list", self.title, self.set_list))

    def set_list(self, hashlist):
        ''' Given a list of infohashes, add and remove torrents 
        from the torrents list as necessary '''
        self.torrents = [self.find_torrent(ih) for ih in hashlist]
        self.olv.AddObjects(filter(lambda to: to not in self.olv.GetObjects(), self.torrents))
        
    def find_torrent(self, infohash):
        for t in self.torrents:
            if t.infohash == infohash:
                return t
        # else make a new torrent object
        t = Torrent(self, infohash)
        for k in t.properties:
            self.joblist.put(t.properties[k][2], t.properties[k][1])
        return t
                
    def on_erase(self, e):
        dlg = wx.MessageDialog(self, "Remove this torrent?", "Delete torrent", 
                               wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            print 'on_erase Not implemented'
        dlg.Destroy()

class Torrent(object):
    """basically a set of properties for OLV"""
    def __init__(self, view, infohash):
        self.view = view
        self.infohash  = infohash 
        self.dirty = False
        self.properties = {
            # 'property': [default_value, job_tuple, frequency]
            'name': ["Loading torrent data...", None, 0],
            'up_rate': [0, None, 0],
            'down_rate': [0, None, 0],
            'ratio': [0, None, 0],
            'size_bytes': [0, None, 0],
            'bytes_done': [0, None, 0],
            'up_total': [0, None, 0],
        }
        for k in self.properties:
            self.properties[k][1] = self.job(k)

        # Don't update these properties after getting them initially
        self.static = ['name', 'size_bytes'] 
        self.new = True # Set to false when torrent is first refreshed
        if view.title == 'stopped':
            self.static.extend(self.properties.keys())
        elif view.title == 'seeding':
            self.static.append('down_rate')

    def __getitem__(self, k):
        """ We stick this in so that ObjectListView thinks it's got a normal dictionary """
        if k in self.properties:
            if self.properties[k]:
                return self.properties[k][0]
            #else:
        else:
            raise KeyError(k)
            
    def job(self, key):
        if not self.properties[key][1]:
            self.properties[key][1] = ("d.get_"+key, self.infohash, self.callback(key))
        return self.properties[key][1]
        
    def callback(self, key):
        def callback(rv): 
            oldvalue = self.properties[key][0]
            self.properties[key][0] = rv
            self.dirty, self.new = True, False
            f = self.new_frequency(key, rv, oldvalue)
            if f:
                self.view.joblist.move(self.properties[key][1], f)
        return callback

    def new_frequency(self, key, new, old):
        """calculates the frequency at which the given key should be updated"""
        if key in self.static:
            return False # do not update this key again
        old_frequency = self.properties[key][2]
        if   key[-4:] == "rate":
            if new == 0: # No transfer happening
                if old_frequency: # not the first time we've updated
                    # slow things down
                    return min(MAX_REFRESH_CYCLE, int(old_frequency * 1.3))
                else:
                    return 5
            else: # Transfer is happening, update more frequently
                return 2
        elif key == "bytes_done":
            if self.properties["down_rate"][0] > 0: # this torrent is transferring data
                # How long we estimate it will take for a visible 0.01 increase
                return max(1, int((1024**int(math.log(new, 1024)) / 100) / self.properties["down_rate"][0]))
            return 8
        else: # Default for everything else
            return 10

    def __repr__(self):
        return "<Torrent - %s>" % self.infohash

#    def __eq__(self, other):
#        return (self.infohash == other.infohash)

class UpdateScheduler(threading.Thread):
    ''' This thread reads the joblist for the current view, 
    and queues up jobs at an appropriate frequency '''
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.notebook = app.frame.notebook
        self.rtorrent = app.rtorrent
        self.proceed = True
    
    def run(self):
        while self.proceed:
            page = self.notebook.GetCurrentPage()
            for i in page.joblist.keys():
                if not i:    # i == 0
                    for job in page.joblist.get(i, clear=True):
                        self.rtorrent.put_first(job)
                    now = int(time.time())
                elif not (now % i):
                    for job in page.joblist.get(i):
                        self.rtorrent.put(job)
            for torrent in page.torrents:
                if torrent.dirty:
                    page.olv.RefreshObject(torrent)
                    torrent.dirty = False
            time.sleep(1)

class LoadTorrentDialog(wx.Dialog):
    ''' Dialog that loads torrents from disk/URL '''
    def __init__(self, remote_root):
        wx.Dialog.__init__(self, None, title="Load torrent", size=(400,400))
        BORDER = 3
        TEXT = wx.EXPAND|wx.ALL
        LABEL = wx.ALIGN_CENTER_VERTICAL|wx.ALL
        BUTTON = wx.ALIGN_RIGHT|wx.ALL

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        file_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filepath_label = wx.StaticText(self, label="From file:")
        self.filepath = wx.TextCtrl(self, TEXT)
        browse_button = wx.Button(self, label="Browse...")
        browse_button.Bind(wx.EVT_BUTTON, self.on_browse)
        file_sizer.Add(filepath_label, 0, LABEL, BORDER)
        file_sizer.Add(self.filepath, 1, TEXT, BORDER)
        file_sizer.Add(browse_button, 0, wx.ALL, BORDER)
        sizer.Add(file_sizer, 0, wx.EXPAND)

        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        url_label = wx.StaticText(self, label="From URL:")
        self.url = wx.TextCtrl(self)
        url_sizer.Add(url_label, 0, LABEL, BORDER)
        url_sizer.Add(self.url, 1, TEXT, BORDER)
        sizer.Add(url_sizer, 0, wx.EXPAND)

        destpath_label = wx.StaticText(self, label="Save in:")
        from browser import PathBrowser
        self.browser = PathBrowser(self, remote_root)
        sizer.Add(destpath_label, 0, LABEL, BORDER)
        sizer.Add(self.browser, 1, TEXT, BORDER)
              
        start_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_immediate = wx.CheckBox(self, label="Start on load")
        start_sizer.Add(self.start_immediate, 1, wx.ALL, BORDER)

        buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, id=wx.ID_OK)
        cancel = wx.Button(self, id=wx.ID_CANCEL)
        buttons_sizer.Add(ok, 0, BUTTON, BORDER)
        buttons_sizer.Add(cancel, 0, BUTTON, BORDER)

        sizer.Add(start_sizer, 0, wx.EXPAND)
        sizer.Add(buttons_sizer, 0, wx.EXPAND)

    def on_browse(self,e):
        ''' Open a file'''
        dlg = wx.FileDialog(self, "Choose a file", os.getcwd(), "", 
                            "*.torrent", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            self.filepath.SetValue(self.dirname+"/"+self.filename)
        dlg.Destroy()

if __name__ == "__main__":
    app = wrtcApp(False)
    # Show configuration window on first run
    if not os.path.isfile(app.settings_manager.config_path):
        app.settings_manager.show_dialog()
    app.MainLoop()
