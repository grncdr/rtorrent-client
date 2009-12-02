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
from rtdaemon import RTDaemon
from Queue import Queue
from multiqueue import MultiQueue

NAME_OF_THIS_APP = 'wrTc'

def format_bytes(bytes, characters=5):
    output = unit = ""
    units = ("KB", "MB", "GB", "TB")
    bytes = float(bytes)
    for i in range(3):
        bytes /= 1024
        if bytes < 1024:
            unit = units[i]
            break
    number = str(int(bytes)).rjust(4)
    return number + unit

class SettingsManager():
    def __init__(self, main_window, defaults={}, config_path=None, load=True):
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

    def save(self, settings):
        ''' Settings should be a simple key value dictionary '''
        for key in settings.keys():
            self.settings.set("DEFAULT", key, settings[key])
        self.settings.write(open(self.config_path,'w'))

    def show_dialog(self, evt):
        dlg = wx.Dialog(self.main_window, title="Settings")
        sizer = wx.FlexGridSizer(4,2,0,10)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)
        sizer.AddGrowableCol(1)
        dlg.SetSizer(sizer)
        for item in self.settings.items("DEFAULT"):
            k = item[0]
            try:
                v = self.settings.getboolean("DEFAULT", k)
            except:
                v = self.settings.get("DEFAULT", k)
            stype = type(v)
            if stype == type(False):
                control = wx.CheckBox(dlg)
                control.SetValue(v)
            elif stype == type('f') or stype == type(u'f') :
                control = wx.TextCtrl(dlg, value=v)
            else:
                continue
            label = wx.StaticText(dlg, label=k.title())
            sizer.Add(label, flag=wx.EXPAND|wx.ALL, border=10)
            sizer.Add(control, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(wx.StaticText(dlg, label=""))
        save = wx.Button(dlg, id=wx.ID_OK, label="Save")
        save.Bind(wx.EVT_BUTTON, self.save)
        sizer.Add(save, 0, wx.ALIGN_RIGHT | wx.ALL, border=10)
        dlg.ShowModal()

class MainWindow(wx.Frame):
    def __init__(self, parent, id, title, job_queue, job_counter):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))
        self.job_queue = job_queue
        self.job_counter = job_counter
        self.settings_manager = SettingsManager(self)

        self.menu_bar = wx.MenuBar()
        self.help_menu = wx.Menu()
        self.help_menu.Append(wx.ID_ABOUT, "&About "+NAME_OF_THIS_APP)
        self.menu_bar.Append(self.help_menu, "&Help")
        self.SetMenuBar(self.menu_bar)
        self.Bind(wx.EVT_MENU, self.on_about_request, id=wx.ID_ABOUT)

        tool_bar = wx.BoxSizer(wx.HORIZONTAL)
        add_torrent_button = wx.Button(self,label="Add torrent")
        add_torrent_button.Bind(wx.EVT_BUTTON, self.load_torrent)
        tool_bar.Add(add_torrent_button, 0, wx.ALIGN_RIGHT, 5)

        settings_button = wx.Button(self,label="Settings")
        settings_button.Bind(wx.EVT_BUTTON, self.settings_manager.show_dialog)
        tool_bar.Add(settings_button, 0, wx.ALIGN_RIGHT, 5)

        self.notebook = TorrentsNotebook(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        main_sizer.Add(tool_bar, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(main_sizer)
        self.Show()
        self.refresher_thread = UpdateScheduler(self.notebook)
        self.refresher_thread.start()

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
            self.job_queue.put((action, argument))
        dlg.Destroy()

    def OnExit(self,e):
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
    columns = [
        {
            "label": "Name", 
            "command": "d.get_name",
            'width': 300, 
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
            "label": "Ratio",
            "command": "d.get_ratio",
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
        for column in self.columns:
            self.InsertColumn(i,column['label'])
            if 'width' in column:
                self.SetColumnWidth(i,column['width'])
            i += 1

    def get_list(self):
        self.job_queue.put(("download_list", self.title, self.set_list))

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
        for i in range(len(self.columns)):
            self.SetStringItem(0, i, self.columns[i]['default'])

    def update_list(self):
        for i in range(self.GetItemCount()):
            infohash = self.map[self.GetItemData(i)]
            for j in range(len(self.columns)):
                item = self.GetItem(i, j)
                if item.GetText() == self.columns[j]['default']:
                    self.job_queue.put((self.columns[j]['command'], infohash,
                                        self.make_callback(i, j)))

    def make_callback(self, i, j):
        def callback(rv): 
            if "formatter" in self.columns[j]:
                rv = self.columns[j]['formatter'](rv)
            self.SetStringItem(i, j, str(rv))
        return callback
                
    def is_complete(self, infohash):
        if r > 0 and v == r:
            return True
        return False

    def on_erase(self, e):
        dlg = wx.MessageDialog(self, "Are you sure you want to remove this torrent?", "Delete torrent", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            self.job_queue.put(("d.erase", self.infohash))
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
    job_counter = MultiQueue()
    job_queue = Queue()
    

    app = wx.PySimpleApp()
    frame = MainWindow(None, wx.ID_ANY, "wrTc - wxPython rTorrent client", 
                       job_queue, job_counter)



    daemon_thread = RTDaemon(job_queue, frame.settings_manager.settings.get("DEFAULT", "rTorrent URL"))

    daemon_thread.start()
    # Do this so that save_settings can stop this thread and start a new one
    frame.daemon_thread = daemon_thread

#    Icons = {}
#    Icons['play'] = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR)
#    Icons['pause'] = wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_TOOLBAR)
#    Icons['add'] = wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR)
#    Icons['remove'] = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_FRAME_ICON)
#    ControlIcons = (Icons['play'], Icons['pause'])

    app.MainLoop()

if __name__ == "__main__":
    fire_it_up()
