#!/usr/bin/python -d

'''
File: wrTc.py
Author: Stephen Sugden (grncdr)
Description: This is a little app that connects to and monitors a remote rTorrent via xmlrpc. It can also upload local torrent files to a remote machine
'''

from __future__ import with_statement
import os, sys, threading, wx, time
from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin
from settings_manager import SettingsManager
from xmlrpcdaemon import XMLRPCDaemon, Binary
from multiqueue import MultiQueue

NAME_OF_THIS_APP = 'wrTc'
WRTC_OSX = (os.uname()[0] == 'Darwin')

def format_bytes(bytes, characters=5):
    ''' prettifies sizes given in bytes '''
    units = ("B", "KB", "MB", "GB", "TB")
    bytes = float(bytes)
    for unit in units:
        if abs(bytes) < 1024:
            break
        bytes /= 1024
    return str(round(bytes,2))+unit

def make_hash(tdata):
    ''' Creates an infohash for the given torrent data, used when loading torrents '''
    from bencode import bdecode, bencode
    from hashlib import sha1
    return sha1(bencode(bdecode(tdata)['info'])).hexdigest().upper()

class wrtcApp(wx.App):
    def __init__(self, *args, **kwargs):
        self.settings_manager = SettingsManager(NAME_OF_THIS_APP+'.cfg', {
            'rtorrent url': 'http://localhost/RPC2', 
            'remote root': '/'
        })
        self.daemon = XMLRPCDaemon(self.settings_manager.get("rTorrent URL"))
        self.daemon.start()
        wx.App.__init__(self, *args, **kwargs)
        self.refresher_thread = UpdateScheduler(self)
        self.refresher_thread.start()
        self.Bind(wx.EVT_ACTIVATE_APP, self.activate)

    def OnInit(self):
        self.frame = MainWindow(None, wx.ID_ANY, NAME_OF_THIS_APP+" - wxPython rTorrent client") 
        self.frame.Show()
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.load_torrent(filename=sys.argv[1])
        return True

    def raise_frame(self):
        try: 
            self.frame.Raise()
        except:
            pass

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
                    self.daemon.jobs.append(('d.start', infohash))
            self.daemon.jobs.append(('d.set_directory', (infohash, dest), 
                               start_callback))
        self.daemon.jobs.append(('load_raw', torrent_data, dest_callback))

class MainWindow(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))

        self.menu_bar = wx.MenuBar()

        self.file_menu = wx.Menu()
        self.file_menu.Append(wx.ID_OPEN, "Add &Torrent")
        self.Bind(wx.EVT_MENU, wx.GetApp().load_torrent, id=wx.ID_OPEN)
        self.file_menu.Append(wx.ID_PREFERENCES, "&Preferences")
        self.Bind(wx.EVT_MENU, wx.GetApp().settings_manager.show_dialog, id=wx.ID_PREFERENCES)
        self.file_menu.Append(wx.ID_EXIT, "&Quit")
        self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
        self.menu_bar.Append(self.file_menu, "&File")

        self.help_menu = wx.Menu()
        self.help_menu.Append(wx.ID_ABOUT, "&About "+NAME_OF_THIS_APP)
        self.Bind(wx.EVT_MENU, self.on_about_request, id=wx.ID_ABOUT)
        self.menu_bar.Append(self.help_menu, "&Help")

        self.SetMenuBar(self.menu_bar)

        self.notebook = TorrentsNotebook(self)
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
        dlg = wx.MessageDialog(self, "wxPython rTorrent client", NAME_OF_THIS_APP, wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()

    def on_exit(self,e):
        wx.GetApp().daemon.proceed = False
        wx.GetApp().refresher_thread.proceed = False
        self.Show(False)
        wx.GetApp().daemon.join()
        wx.GetApp().refresher_thread.join()
        self.Destroy()


class TorrentsNotebook(wx.Notebook):
    def __init__(self, parent, *args, **kwargs):
        wx.Notebook.__init__(self, parent, *args, **kwargs)
        self.views_to_load = ["incomplete", "seeding", "stopped"]
        self.load_views()
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.page_changed)

    def load_views(self):
        self.DeleteAllPages()
        for view in self.views_to_load:
            self.AddPage(rTorrentView(self, view), view.capitalize());

    def page_changed(self, evt):
        self.GetPage(evt.GetSelection()).refresh()
        evt.Skip()

class rTorrentView(ListCtrlAutoWidthMixin, wx.ListView):
    _columns = [
        {
            "label": "Name", 
            "command": "d.get_name",
            'width': 200, 
            "default": "Loading torrent data...",
            "frequency": 0,
        }, 
        {
            "label": "Up Rate",
            "command": "d.get_up_rate",
            "default": "N/A",
            "formatter": format_bytes,
        },
        {
            "label": "Down Rate",
            "command": "d.get_down_rate",
            "default": "N/A",
            "formatter": format_bytes,
        },
        {
            "label": "Size",
            "command": "d.get_size_bytes",
            "default": "N/A",
            "formatter": format_bytes,
            "frequency": 0,
        },
        {
            "label": "Uploaded",
            "command": "d.get_up_total",
            "default": "N/A",
            "formatter": format_bytes,
        },
        {
            "label": "Downloaded",
            "command": "d.get_bytes_done",
            "default": "N/A",
            "formatter": format_bytes,
        },
        {
            "label": "Ratio",
            "command": "d.get_ratio",
            "formatter": lambda p: str(p)+"%",
            "default": "N/A",
            "width": 45,
            "default": "N/A", 
            "frequency": 20,
        },
        {
            "label": "S",
            "command": "d.get_peers_complete",
            "width": 25,
            "default": "N/A",
            "frequency": 20
        },
        {
            "label": "P",
            "command": "d.get_peers_accounted",
            "width": 25,
            "default": "N/A",
            "frequency": 10
        },
    ]
    def __init__(self, parent, title="default"):
        wx.ListView.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.tag_map = {}
        self.title = title
        for column in self._columns:
            self.InsertColumn(self.GetColumnCount(), column['label'])
        ListCtrlAutoWidthMixin.__init__(self)
        if WRTC_OSX:
            self.setResizeColumn(1)
        else:
            self.setResizeColumn(0)
        self.joblist = MultiQueue()
        self.joblist.put(0, ("download_list", self.title, self.set_list))
        self.joblist.put(5, ("download_list", self.title, self.set_list))

    def __repr__(self):
        return "rTorrentView(wx.ListView) - "+self.title.capitalize()

    def refresh(self):
        ''' Clear the queue and update the current page, called on page change '''
        queue = wx.GetApp().daemon.jobs
        queue.clear()
        queue.append(('download_list', self.title, self.set_list ))

    def set_list(self, hashlist):
        ''' Given a list of infohashes, add and remove torrents from the listctrl as necessary '''
        addList = [val for val in hashlist if val not in self.tag_map.values()]
        rmList = [tag for (tag, hash) in self.tag_map.items() if hash not in hashlist] 
        for id in rmList:
            self.DeleteItem(self.FindItemData(-1, id))
            self.joblist.remove(lambda job: job[1] == self.tag_map[id])
            del(self.tag_map[id])
        for infohash in addList:
            self.add_torrent(infohash)
        
    def add_torrent(self, infohash):
        ''' Add a new torrent to the listctrl '''
        tag = wx.NewId()
        self.tag_map[tag] = infohash
        self.Append([c['default'] for c in self._columns])
        self.SetItemData(self.GetItemCount()-1, tag)
        for (i, c) in zip(range(len(self._columns)), self._columns):
            self.SetStringItem(0, i, c['default'])
            if 'frequency' in c:
                f = c['frequency']
            else:
                f = 3
            self.joblist.put(f, (c['command'], infohash, self.make_callback(tag, i)))

    def make_callback(self, tag, col):
        ''' Returns a function that will update the given list item with the value returned by rTorrent '''
        def callback(rv): 
            row = self.FindItemData(-1, tag)
            if "formatter" in self._columns[col]:
                rv = self._columns[col]['formatter'](rv)
            else:
                rv = str(rv)
            try: # Occasionally we try to update an item after it has been removed
                self.SetStringItem(row, col, rv)
            except wx.PyAssertionError: #Wish this threw something a bit less generic...
                return
        return callback
                
    def on_erase(self, e):
        dlg = wx.MessageDialog(self, "Are you sure you want to remove this torrent?", "Delete torrent", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            print 'Not implemented'
        dlg.Destroy()

class UpdateScheduler(threading.Thread):
    ''' This thread reads the joblist for the current view, 
    and queues up jobs at an appropriate frequency '''
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.notebook = app.frame.notebook
        self.remote_queue = app.daemon.jobs
        self.proceed = True
    
    def run(self):
        while self.proceed:
            job_list = self.notebook.GetCurrentPage().joblist
            immediate = job_list.get(0, clear=True)
            for job in immediate:
                self.remote_queue.appendleft(job)
            now = int(time.time())
            if len(job_list) == 0:
                time.sleep(1)
                continue
            for i in job_list.keys():
                if not (now % i):
                    for job in job_list.get(i):
                        self.remote_queue.append(job)
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
        dlg = wx.FileDialog(self, "Choose a file", os.getcwd(), "", "*.torrent", wx.OPEN)
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
