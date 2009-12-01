#!/usr/bin/python -d

'''
File: rtorrent-client.py
Author: Stephen Sugden (grncdr)
Description: This is a little app that connects to and monitors a remote rTorrent via xmlrpc, with nice progress bars and the like, as well as handling torrents on the local machine by uploading them to the remote rTorrent instance
'''

import os, sys, threading, wx
from time import sleep
from ConfigParser import ConfigParser
from wx.lib import scrolledpanel as sp
from callbackeventhandler import CallbackEvent, CallbackEventHandler
from rtdaemon import RTDaemon
from controls import *

class SettingsManager():
    def __init__(self, defaults={}, config_path=None, load=True):
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



class MainWindow(wx.Frame):
    def __init__(self, parent, id, title, job_queue, job_counter):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))
        self.job_queue = job_queue
        self.job_counter = job_counter
        tool_bar = wx.BoxSizer(wx.HORIZONTAL)
        add_torrent_button = wx.Button(self,label="Add torrent")
        add_torrent_button.Bind(wx.EVT_BUTTON, self.load_torrent)
        tool_bar.Add(add_torrent_button, 0, wx.ALIGN_RIGHT, 5)

        self.notebook = TorrentsNotebook(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        main_sizer.Add(tool_bar, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(main_sizer)
        self.Show()
        self.refresher_thread = UpdateScheduler(self.notebook)
        self.refresher_thread.start()

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

    def queue_setup(self, child):
        ''' Takes an object and attaches the queues and their methods to it, avoids the need for a global queue object '''
        child.job_queue = self.job_queue
        child.job_counter = self.job_counter
        child.init_queues = self.init_queues
        child.queue_setup = self.queue_setup

    def OnExit(self,e):
        self.init_queues()
        self.Destroy()


class TorrentsNotebook(wx.Notebook):
    def __init__(self, parent, *args, **kwargs):
        wx.Notebook.__init__(self, parent, *args, **kwargs)
        parent.queue_setup(self)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChange)
        self.views_to_load = ["incomplete", "seeding", "stopped"]
        self.load_views()
        self.settings_panel = SettingsPanel(self)
        self.AddPage(self.settings_panel, 'Settings')

    def OnPageChange(self, event):
        page = self.GetPage(event.GetSelection())
        self.init_queues()
        if page and hasattr(page, "torrents"):
            page.synchronize()
        event.Skip()
        
    def load_views(self):
        self.DeleteAllPages()
        for view in self.views_to_load:
            self.AddPage(ViewPanel(self, view), view.capitalize());


class ViewPanel(sp.ScrolledPanel):
    def __init__(self, parent, title="default"):
        sp.ScrolledPanel.__init__(self, parent)
        parent.queue_setup(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.torrents = {}
        self.title = title
        self.SetSizer(sizer)
        self.Bind(wx.EVT_SCROLLWIN, self.OnScroll)

    def add_to_view(self, hashlist):
        for infohash in hashlist:
            if infohash not in self.job_counter:
                self.job_counter.changecount(infohash)
            self.torrents[infohash] = TorrentPanel(self, infohash)
            self.GetSizer().Add(self.torrents[infohash], 0, wx.TOP | wx.BOTTOM | wx.EXPAND, 3)
        self.SetupScrolling()

    def remove_from_view(self, hashlist):
        for infohash in hashlist:
            panel = self.torrents[infohash]
            del self.torrents[infohash]
            panel.Show(False)
            panel.Destroy()
        self.SetupScrolling()

    def OnScroll(self, event):
        event.Skip()
        self.init_queues()

    def update_visible(self):
        for child in self.GetChildren():
            child.Update()
      
    def synchronize(self):
        self.job_queue.put(("download_list", self.title, CallbackEvent(method=self.update_list)))

    def update_list(self, new_hashlist):
        current_hashlist = self.torrents.keys()
        addList = [val for val in new_hashlist if val not in current_hashlist]
        rmList = [val for val in current_hashlist if val not in new_hashlist]
        if len(rmList):
            self.remove_from_view(rmList)
        if len(addList):
            self.add_to_view(addList)
        if len(current_hashlist) != len(self.torrents.keys()):
            self.GetSizer().Layout()

class TorrentPanel(wx.Panel):
    def __init__(self, parent, infohash):
        wx.Panel.__init__(self, parent, style=wx.RAISED_BORDER)
        parent.queue_setup(self)
        self.infohash = infohash

        # Create sizers
        TopSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(TopSizer)
        InfoSizer = wx.BoxSizer(wx.VERTICAL)
        TopSizer.Add(InfoSizer, 1, wx.EXPAND | wx.ALL, 2)
        LnTSizer = wx.BoxSizer(wx.HORIZONTAL)
        RnPSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.progress_bar = RemoteProgressBar(self)
        self.upload_rate_label = RemoteLabel(self,
                                             "d.get_up_rate", "0", "Up: %s/s", format_bytes, True)
        self.download_rate_label = RemoteLabel(self, 
                                               "d.get_down_rate", "0", 
                                               "Down: %s/s", format_bytes, True)

        self.start_stop_button = StateButton(self, self.start_stop, ControlIcons)

        self.title_label = RemoteLabel(self, 
                                       "d.get_base_filename", 
                                       "Loading Torrent Info...")
        
        self.erase_button = wx.BitmapButton(self, wx.ID_ANY, Icons['remove'])
        self.erase_button.Bind(wx.EVT_BUTTON, self.on_erase)
        RnPSizer.Add(self.progress_bar, 1, wx.EXPAND)
        RnPSizer.Add(self.upload_rate_label, 0, wx.ALIGN_CENTER | wx.LEFT, 3)
        RnPSizer.Add(self.download_rate_label, 0, wx.ALIGN_CENTER)


        LnTSizer.Add(self.title_label, 1, wx.EXPAND | wx.CENTRE | wx.TOP | wx.BOTTOM, 3)
        LnTSizer.Add(self.erase_button, 0, wx.ALIGN_RIGHT | wx.ALL, 2)
        InfoSizer.Add(LnTSizer, 0, wx.EXPAND)
        InfoSizer.Add(RnPSizer, 0, wx.EXPAND)
        TopSizer.Prepend(self.start_stop_button, 0, wx.ALIGN_CENTER | wx.ALL, 2)
        self.update()

    def update(self):
        if self.title_label.GetLabel() == "Loading Torrent Info...":
            self.title_label.update_self("label")
        self.start_stop_button.update_self("bitmap")
        self.upload_rate_label.update_self("label")
        if not self.progress_bar.GetRange():
            self.progress_bar.update_self("range")
        if not self.is_complete():
            self.download_rate_label.update_self("label")
            self.progress_bar.update_self("value")

    def is_complete(self):
        v = self.progress_bar.GetValue()
        r = self.progress_bar.GetRange()
        if r > 0 and v == r:
            return True
        return False

    def start_stop(self, button):
        if button.GetBitmapLabel() == ControlIcons[0]:
            job_queue.put(("d.start", self.infohash))
        elif button.GetBitmapLabel() == ControlIcons[1]:
            job_queue.put(("d.stop", self.infohash))

    def on_erase(self, e):
        dlg = wx.MessageDialog(self, "Are you sure you want to remove this torrent?", "Delete torrent", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            job_queue.put(("d.erase", self.infohash))
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
            self.notebook.GetCurrentPage().update_visible()
            self.notebook.GetCurrentPage().synchronize()
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


class SettingsPanel(sp.ScrolledPanel):
    def __init__(self, parent):
        sp.ScrolledPanel.__init__(self, parent)
        self.settings_manager = SettingsManager({ "rTorrent URL": "http://localhost/RPC2", "Remote Browse URL": "", "Enable remote browse": "no" })
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        padding = 3
        settings = {}
        for item in self.settings_manager.settings.items("DEFAULT"):
            k = item[0]
            try:
                v = self.settings_manager.settings.getboolean("DEFAULT", k)
            except:
                v = self.settings_manager.settings.get("DEFAULT", k)
            settings[k] = {}
            stype = type(v)
            if stype == type(False):
                settings[k]["ctrl"] = wx.CheckBox(self)
                settings[k]["ctrl"].SetValue(v)
            elif stype == type('f') or stype == type(u'f') :
                settings[k]["ctrl"] = wx.TextCtrl(self, value=v)
            else:
                continue
            settings[k]["label"] = wx.StaticText(self, label=k.title())
            settings[k]["sizer"] = wx.BoxSizer(wx.HORIZONTAL)
            settings[k]["sizer"].Add(settings[k]["label"], 1, wx.EXPAND)
            settings[k]["sizer"].Add(settings[k]["ctrl"], 3, wx.EXPAND)
            sizer.Add(settings[k]["sizer"], 0, wx.EXPAND)
        self.settings = settings

        save = wx.Button(self, id=wx.ID_OK, label="Save")
        save.Bind(wx.EVT_BUTTON, self.save_settings)
        sizer.Add(save, 0, wx.ALIGN_RIGHT | wx.ALL, padding)

    def save_settings(self, evt):
        new_settings = {}
        for name in self.settings.keys():
            new_settings[name] = self.settings[name]["ctrl"].GetValue()
        print "Saving Settings:", new_settings
        self.settings_manager.save(new_settings)
        frame = self.GetGrandParent()
        frame.init_queues()
        frame.daemon_thread.open(self.settings_manager.settings.get("DEFAULT", "rTorrent URL"))
        

    def update_visible(self):
        ''' This is a NOP because the GUI updater attempts to update the settings page'''
        return True

    synchronize = update_visible

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

def fire_it_up():
    job_counter = MultiQueue()
    job_queue = Queue()
    

    app = wx.PySimpleApp()
    frame = MainWindow(None, wx.ID_ANY, "wrTc - wxPython rTorrent client", 
                       job_queue, job_counter)

    settings_manager = frame.notebook.settings_panel.settings_manager

    callback_event_handler = CallbackEventHandler("infohash", job_counter.dec)
    daemon_thread = RTDaemon(job_queue, callback_event_handler,
                             settings_manager.settings.get("DEFAULT", "rTorrent URL"))

    daemon_thread.start()
    # Do this so that save_settings can stop this thread and start a new one
    frame.daemon_thread = daemon_thread

    global Icons, ControlIcons
    Icons = {}
    Icons['play'] = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR)
    Icons['pause'] = wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_TOOLBAR)
    Icons['add'] = wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR)
    Icons['remove'] = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_FRAME_ICON)
    ControlIcons = (Icons['play'], Icons['pause'])

    app.MainLoop()

if __name__ == "__main__":
    fire_it_up()
