#!/usr/bin/python -d

'''
File: wrTc.py
Author: Stephen Sugden (grncdr)
Description: This is a little app that connects to and monitors a remote rTorrent via xmlrpc. It can also upload local torrent files to a remote machine
'''

import os, sys, threading, wx, time
from ConfigParser import ConfigParser
from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin
from rtdaemon import rTDaemon
from collections import deque
from multiqueue import MultiQueue

NAME_OF_THIS_APP = 'wrTc'

def format_bytes(bytes, characters=5):
    units = ("B", "KB", "MB", "GB", "TB")
    bytes = float(bytes)
    for unit in units:
        if abs(bytes) < 1024:
            break
        bytes /= 1024
    return str(round(bytes,2))+unit

class SettingsManager():
    def __init__(self, main_window, defaults={'rtorrent url': 'http://localhost/RPC2', 'remote root': '/'}, config_path=None, load=True):
        self.main_window = main_window
        self.settings = ConfigParser(defaults)
        if load:
            if not config_path:
                self.config_path = self.get_default_config_path()
            self.settings.read(self.config_path)

    def get_default_config_path(self):
        if os.name == 'nt':
            config_path = os.path.expanduser("~\AppData\Local\wrtc.rc")
        else:
            config_path = os.path.expanduser("~/.config/wrtc.rc")
        return config_path

    def show_dialog(self, evt):
        self.dlg = wx.Dialog(self.main_window, title="Settings")
        sizer = wx.FlexGridSizer(4,2,0,10)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)
        sizer.AddGrowableCol(1)
        self.dlg.SetSizer(sizer)
        self.controls = [] 
        for item in self.settings.items("DEFAULT"):
            k = item[0]
            try:
                v = self.settings.getboolean("DEFAULT", k)
            except:
                v = self.settings.get("DEFAULT", k)
            stype = type(v)
            if stype == type(False):
                control = wx.CheckBox(self.dlg)
                control.SetValue(v)
            elif stype == type('f') or stype == type(u'f') :
                control = wx.TextCtrl(self.dlg, value=v)
            else:
                continue
            label = wx.StaticText(self.dlg, label=k.title())
            self.controls.append((k, control,))
            sizer.Add(label, flag=wx.EXPAND|wx.ALL, border=10)
            sizer.Add(control, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(wx.StaticText(self.dlg, label=""))
        save_button = wx.Button(self.dlg, id=wx.ID_OK, label="Save")
        save_button.Bind(wx.EVT_BUTTON, self.save)
        sizer.Add(save_button, 0, wx.ALIGN_RIGHT | wx.ALL, border=10)
        self.dlg.ShowModal()

    def save(self, evt):
        for setting, control in self.controls:
            self.settings.set("DEFAULT", setting, str(control.GetValue()))
        try:
            fh = open(self.config_path,'wb')
            self.settings.write(fh)
        finally:
            fh.close()
        self.main_window.daemon_thread.open(self.settings.get("DEFAULT",'rTorrent URL'))
        self.dlg.Close()

class MainWindow(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))
        self.job_queue = deque()
        self.settings_manager = SettingsManager(self)
        self.daemon_thread = rTDaemon(self.job_queue, self.settings_manager.settings.get("DEFAULT", "rTorrent URL"))
        self.daemon_thread.start()
        self.create_interface()
        self.Show()
        self.refresher_thread = UpdateScheduler(self.notebook)
        self.refresher_thread.start()
        self.Bind(wx.EVT_CLOSE, self.on_exit)

    def create_interface(self):
        self.menu_bar = wx.MenuBar()

        self.file_menu = wx.Menu()
        self.file_menu.Append(wx.ID_OPEN, "Add &Torrent")
        self.Bind(wx.EVT_MENU, self.load_torrent, id=wx.ID_OPEN)
        self.file_menu.Append(wx.ID_PREFERENCES, "&Preferences")
        self.Bind(wx.EVT_MENU, self.settings_manager.show_dialog, id=wx.ID_PREFERENCES)
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
#    Icons = {}
#    Icons['play'] = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR)
#    Icons['pause'] = wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_TOOLBAR)
#    Icons['add'] = wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR)
#    Icons['remove'] = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_FRAME_ICON)
#    ControlIcons = (Icons['play'], Icons['pause'])

    def on_about_request(self, evt):
        dlg = wx.MessageDialog(self, "wxPython rTorrent client", NAME_OF_THIS_APP, wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()

    def load_torrent(self,e=None,filename=None):
        dlg = LoadTorrentDialog(self)
        if filename:
            dlg.filepath.SetValue(filename)
        if dlg.ShowModal() == wx.ID_OK:
            start = dlg.start_immediate.GetValue()
            dest = dlg.browser.GetPyData(dlg.browser.GetSelection())['path']
            if dlg.filepath.GetValue() != '':
                self.daemon_thread.send_torrent(dlg.filepath.GetValue(), start, dest)
            elif dlg.url.GetValue() != '':
                self.daemon_thread.send_torrent(dlg.url.GetValue(), start, dest, True)
        dlg.Destroy()

    def on_exit(self,e):
        self.daemon_thread.proceed = False
        self.refresher_thread.proceed = False
        self.Show(False)
        time.sleep(2)
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
            self.AddPage(ViewPanel(self, view), view.capitalize());
        self.page_changed()

    def page_changed(self, evt=None):
        if evt:
            evt.Skip()
            page = self.GetPage(evt.GetSelection())
        else:
            page = self.GetCurrentPage()
        queue = self.GetTopLevelParent().job_queue
        queue.clear()
        queue.append(('download_list', page.title, page.set_list ))

class ViewPanel(ListCtrlAutoWidthMixin, wx.ListView):
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
            "frequency": 0
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
            "frequency": 10
        },
        {
            "label": "S",
            "command": "d.get_peers_complete",
            "width": 25,
            "default": "N/A",
            "frequency": 10
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
        ListCtrlAutoWidthMixin.__init__(self)
        self.setResizeColumn(0)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.tag_map = {}
        self.title = title
        self.create_columns()
        self.joblist = MultiQueue()
        self.joblist.put(5, ("download_list", self.title, self.set_list))

    def __repr__(self):
        return "rTorrent View (wx.ListView) - "+self.title.capitalize()

    def create_columns(self):
        i = 0
        for column in self._columns:
            self.InsertColumn(i,column['label'])
            if 'width' in column:
                self.SetColumnWidth(i,column['width'])
            i += 1

    def set_list(self, hashlist):
        addList = [val for val in hashlist if val not in self.tag_map.values()]
        rmList = [tag for (tag, hash) in self.tag_map.items() if hash not in hashlist] 
        for id in rmList:
            self.DeleteItem(self.FindItemData(-1, id))
            self.joblist.remove(lambda job: job[1] == self.tag_map[id])
            del(self.tag_map[id])
        for infohash in addList:
            self.add_torrent(infohash)
        
    def add_torrent(self, infohash):
        tag = wx.NewId()
        self.tag_map[tag] = infohash
        self.InsertStringItem(0, 'If you are seeing this, an error has occured ;)')
        self.SetItemData(0, tag)
        for (i, c) in zip(range(len(self._columns)), self._columns):
            self.SetStringItem(0, i, c['default'])
            if 'frequency' in c:
                f = c['frequency']
            else:
                f = 3
            self.joblist.put(f, (c['command'], infohash, self.make_callback(tag, i)))

    def make_callback(self, tag, col):
        def callback(rv): 
            row = self.FindItemData(-1, tag)
            if "formatter" in self._columns[col]:
                rv = self._columns[col]['formatter'](rv)
            else:
                rv = str(rv)
            self.SetStringItem(row, col, rv)
        return callback
                
    def on_erase(self, e):
        dlg = wx.MessageDialog(self, "Are you sure you want to remove this torrent?", "Delete torrent", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            print 'Not implemented'
        dlg.Destroy()

class UpdateScheduler(threading.Thread):
    ''' This thread reads the joblist for the current view, 
    and queues up jobs at an appropriate frequency '''
    def __init__(self, notebook):
        threading.Thread.__init__(self)
        self.notebook = notebook
        self.remote_queue = notebook.GetTopLevelParent().job_queue
        self.proceed = True
    
    def run(self):
        while self.proceed:
            job_list = self.notebook.GetCurrentPage().joblist
            immediate = job_list.get(0, clear=True)
            self.add_jobs(immediate)
            now = int(time.time())
            if len(job_list) == 0:
                time.sleep(1)
                continue
            for i in job_list.keys():
                if not (now % i):
                    list = job_list.get(i)
                    self.add_jobs(list)
            time.sleep(1)

    def add_jobs(self, list):
        for job in list:
            self.remote_queue.append(job)

class LoadTorrentDialog(wx.Dialog):
    def __init__(self, parent_window):
        wx.Dialog.__init__(self, None, wx.ID_ANY, "Load torrent")
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        padding = 3
  
        file_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filepath_label = wx.StaticText(self, label="From file:")
        self.filepath = wx.TextCtrl(self)
        browse_button = wx.Button(self, label="Browse...")
        browse_button.Bind(wx.EVT_BUTTON, self.OnBrowse)
        file_sizer.AddMany([(filepath_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, padding), (self.filepath, 1, wx.EXPAND | wx.ALL, padding),(browse_button, 0, wx.ALL, padding)])

        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        url_label = wx.StaticText(self, label="From URL:")
        self.url = wx.TextCtrl(self)
        url_sizer.AddMany([(url_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, padding), (self.url, 1, wx.EXPAND | wx.ALL, padding)])
        sizer.AddMany([(file_sizer, 0, wx.EXPAND),(url_sizer, 0, wx.EXPAND)])

        destpath_label = wx.StaticText(self, label="Save in:")
        from browser import PathBrowser
        self.browser = PathBrowser(self, parent_window)
        sizer.AddMany([(destpath_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, padding), (self.browser, 1, wx.EXPAND | wx.ALL, padding)])
              
        start_sizer = wx.BoxSizer(wx.HORIZONTAL)
        start_label = wx.StaticText(self, label="Start on load")
        self.start_immediate = wx.CheckBox(self)
        start_sizer.AddMany([(start_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, padding), (self.start_immediate, 1, wx.ALL, padding)])

        buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, id=wx.ID_OK)
        cancel = wx.Button(self, id=wx.ID_CANCEL)
        buttons_sizer.AddMany([(ok, 0, wx.ALIGN_RIGHT | wx.ALL, padding),(cancel, 0, wx.ALIGN_RIGHT | wx.ALL, padding)])

        sizer.AddMany([(start_sizer, 0, wx.EXPAND),(buttons_sizer, 0, wx.EXPAND)])

    def OnBrowse(self,e):
        ''' Open a file'''
        dlg = wx.FileDialog(self, "Choose a file", os.getcwd(), "", "*.torrent", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            self.filepath.SetValue(self.dirname+"/"+self.filename)
        dlg.Destroy()

if __name__ == "__main__":
    app = wx.PySimpleApp()
    frame = MainWindow(None, wx.ID_ANY, NAME_OF_THIS_APP+" - wxPython rTorrent client") 
    app.MainLoop()
