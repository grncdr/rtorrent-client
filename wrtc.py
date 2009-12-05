#!/usr/bin/python -d

'''
File: wrTc.py
Author: Stephen Sugden (grncdr)
Description: This is a little app that connects to and monitors a remote rTorrent via xmlrpc. It can also upload local torrent files to a remote machine
'''

import os, sys, threading, wx
from time import sleep
from ConfigParser import ConfigParser
from wx.lib import scrolledpanel as sp
from rtdaemon import rTDaemon
from Queue import Queue
from multiqueue import MultiQueue

NAME_OF_THIS_APP = 'wrTc'

def format_bytes(bytes, characters=5):
    units = ("B", "KB", "MB", "GB", "TB")
    bytes = float(bytes)
    for unit in units:
        if bytes < 1024:
            break
        bytes /= 1024
    return str(round(bytes,2))+unit

class SettingsManager():
    def __init__(self, main_window, defaults={'rtorrent url': 'http://localhost/RPC2'}, config_path=None, load=True):
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
        with open(self.config_path,'wb') as fh:
            self.settings.write(fh)
        self.main_window.daemon_thread.open(self.settings.get("DEFAULT",'rTorrent URL'))
        self.dlg.Close()

class MainWindow(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))
        self.job_counter = MultiQueue()
        self.job_queue = Queue()
        self.settings_manager = SettingsManager(self)
        self.daemon_thread = rTDaemon(self.job_queue, self.settings_manager.settings.get("DEFAULT", "rTorrent URL"))
        self.daemon_thread.start()
        self.create_interface()
        self.Show()
        self.refresher_thread = UpdateScheduler(self.notebook)
        self.refresher_thread.start()

    def create_interface(self):
        self.menu_bar = wx.MenuBar()

        self.file_menu = wx.Menu()
        self.file_menu.Append(wx.ID_OPEN, "Add &Torrent")
        self.Bind(wx.EVT_MENU, self.load_torrent, id=wx.ID_OPEN)
        self.file_menu.Append(wx.ID_PREFERENCES, "&Preferences")
        self.Bind(wx.EVT_MENU, self.settings_manager.show_dialog, id=wx.ID_PREFERENCES)
        self.file_menu.Append(wx.ID_EXIT, "&Quit")
        self.Bind(wx.EVT_MENU, self.quit, id=wx.ID_EXIT)
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

    def quit(self, evt):
        self.Destroy()

    def on_about_request(self, evt):
        dlg = wx.MessageDialog(self, "wxPython rTorrent client", NAME_OF_THIS_APP, wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()

    def init_queues(self):
        try:
            self.job_queue.mutex.acquire()
            self.job_queue.queue.clear()
            self.job_queue.mutex.release()
        except:
            print("Ah fuck")
            sleep(10)
            quit()
        self.job_counter.__init__()

    def load_torrent(self,e=None,filename=None):
        dlg = LoadTorrentDialog()
        if filename:
            dlg.filepath.SetValue(filename)
        if dlg.ShowModal() == wx.ID_OK:
            action = "load"
            if dlg.filepath.GetValue() != '':
                action += "_raw"
                argument = self.get_torrent_data(dlg.filepath.GetValue())
            elif dlg.url.GetValue() != '':
                argument = dlg.url.GetValue()
            if dlg.start_immediate.GetValue():
                action += "_start"
            self.job_queue.put((1, action, argument))
        dlg.Destroy()

    def OnExit(self,e):
        del(self.daemon_thread)
        self.init_queues()
        self.Destroy()


class TorrentsNotebook(wx.Notebook):
    def __init__(self, parent, *args, **kwargs):
        wx.Notebook.__init__(self, parent, *args, **kwargs)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChange)
        self.views_to_load = ["incomplete", "seeding", "stopped"]
        self.load_views()

    def OnPageChange(self, event):
        page = self.GetPage(event.GetSelection())
        self.GetTopLevelParent().init_queues()
        if page and hasattr(page, "torrents"):
            page.synchronize()
        event.Skip()
        
    def load_views(self):
        self.DeleteAllPages()
        for view in self.views_to_load:
            self.AddPage(ViewPanel(self, view), view.capitalize());


class ViewPanel(wx.ListView):
    _columns = [
        {
            "label": "Name", 
            "command": "d.get_name",
            'width': 200, 
            "default": "Loading torrent data..."
        }, 
        {
            "label": "Progress",
            "command": "d.get_complete",
            "default": "N/A",
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
            "label": "Uploaded",
            "command": "d.get_up_total",
            "default": "N/A",
            "formatter": format_bytes,
        },
        {
            "label": "Downloaded",
            "command": "d.get_down_total",
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
        },
        {
            "label": "S",
            "command": "d.get_peers_complete",
            "width": 25,
            "default": "N/A",
        },
        {
            "label": "P",
            "command": "d.get_peers_accounted",
            "width": 25,
            "default": "N/A",
        },
    ]
    def __init__(self, parent, title="default"):
        wx.ListView.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.map = {}
        self.title = title
        self.create_columns()
        self.job_queue = self.GetTopLevelParent().job_queue
        self.job_counter = self.GetTopLevelParent().job_counter

    def create_columns(self):
        i = 0
        for column in self._columns:
            self.InsertColumn(i,column['label'])
            if 'width' in column:
                self.SetColumnWidth(i,column['width'])
            i += 1

    def get_list(self):
        self.job_queue.put((8, "download_list", self.title, self.set_list))

    def set_list(self, hashlist):
        addList = [val for val in hashlist if val not in self.map.values()]
        rmList = [val for val in self.map.values() if val not in hashlist]
        for infohash in rmList:
            self.DeleteItem(self.FindItemData([(v, k) for (k, v) in self.map][infohash]))
        for infohash in addList:
            self.add_torrent(infohash)
        self.update_list()
        
    def add_torrent(self, infohash):
        id = wx.NewId()
        self.map[id] = infohash
        if infohash not in self.job_counter:
            self.job_counter.changecount(infohash)
        self.InsertStringItem(0, 'If you are seeing this, an error has occured ;)')
        self.SetItemData(0, id)
        for i in range(len(self._columns)):
            self.SetStringItem(0, i, self._columns[i]['default'])

    def update_list(self):
        for i in range(self.GetItemCount()):
            infohash = self.map[self.GetItemData(i)]
            for j in range(len(self._columns)):
                item = self.GetItem(i, j)
                if item.GetText() == self._columns[j]['default']:
                    self.job_queue.put((3, self._columns[j]['command'], infohash,
                                        self.make_callback(i, j)))

    def make_callback(self, i, j):
        def callback(rv): 
            if "formatter" in self._columns[j]:
                rv = self._columns[j]['formatter'](rv)
            self.SetStringItem(i, j, str(rv))
        return callback
                
    def is_complete(self, infohash):
        if r > 0 and v == r:
            return True
        return False

    def on_erase(self, e):
        dlg = wx.MessageDialog(self, "Are you sure you want to remove this torrent?", "Delete torrent", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            self.job_queue.put((1, "d.erase", self.infohash))
            sizer = self.GetParent().GetSizer()
            self.Destroy()
            sizer.Layout()
        dlg.Destroy()

class UpdateScheduler(threading.Thread):
    def __init__(self, notebook):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.notebook = notebook
    
    def run(self):
        while True:
            self.notebook.GetCurrentPage().get_list()
            sleep(2)

class LoadTorrentDialog(wx.Dialog):
    def __init__(self):
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

        dest_sizer = wx.BoxSizer(wx.HORIZONTAL)
        destpath_label = wx.StaticText(self, label="Save in:")
        self.destpath = wx.TextCtrl(self)
        dest_sizer.AddMany([(destpath_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, padding), (self.destpath, 1, wx.EXPAND | wx.ALL, padding)])
              
        start_sizer = wx.BoxSizer(wx.HORIZONTAL)
        start_label = wx.StaticText(self, label="Start on load")
        self.start_immediate = wx.CheckBox(self)
        start_sizer.AddMany([(start_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, padding), (self.start_immediate, 1, wx.ALL, padding)])

        buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, id=wx.ID_OK)
        cancel = wx.Button(self, id=wx.ID_CANCEL)
        buttons_sizer.AddMany([(ok, 0, wx.ALIGN_RIGHT | wx.ALL, padding),(cancel, 0, wx.ALIGN_RIGHT | wx.ALL, padding)])

        sizer.AddMany([(file_sizer, 0, wx.EXPAND),(url_sizer, 0, wx.EXPAND),(dest_sizer, 0, wx.EXPAND),(start_sizer, 0, wx.EXPAND),(buttons_sizer, 0, wx.EXPAND)])

    def OnBrowse(self,e):
        ''' Open a file'''
        dlg = wx.FileDialog(self, "Choose a file", os.getcwd(), "", "*.torrent", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            self.filepath.SetValue(self.dirname+"/"+self.filename)
        dlg.Destroy()

def fire_it_up():
    app = wx.PySimpleApp()
    frame = MainWindow(None, wx.ID_ANY, NAME_OF_THIS_APP+" - wxPython rTorrent client") 

#    Icons = {}
#    Icons['play'] = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR)
#    Icons['pause'] = wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_TOOLBAR)
#    Icons['add'] = wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR)
#    Icons['remove'] = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_FRAME_ICON)
#    ControlIcons = (Icons['play'], Icons['pause'])

    app.MainLoop()

if __name__ == "__main__":
    fire_it_up()
