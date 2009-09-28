#!/usr/bin/python -d

"""
This is a little app that connects to and monitors a remote rTorrent via xmlrpc, with nice progress bars and the like, as well as handling torrents on the local machine by uploading them to the remote rTorrent instance
"""

import os, sys, threading, time, wx, pickle
from wx.lib import scrolledpanel as sp
import callbackeventcatcher as cbec
from rtdaemon import RTDaemon
from controls import *
from xmlrpclib import ServerProxy, Binary

class wrtc(wx.App):
    Settings = { "URL": "http://localhost:5000/RPC2", "REMOTE_BROWSE_URL": " ", "REMOTE_BROWSE_ENABLE": False }
    if os.name == 'nt':
        ConfigPath = os.path.expanduser("~\AppData\Local\wrtc.rc")
    else:
        ConfigPath = os.path.expanduser("~/.config/wrtc.rc")
    Proxy = None
    Icons = {}
    Title = "wrTc - wxPython rTorrent client"

    def OnInit(self):
        wrtc.LoadIcons()
        wrtc.LoadSettings()

        frame = MainWindow( None, wx.ID_ANY, wrtc.Title )
        self.SetTopWindow(frame)
        wrtc.Proxy = ServerProxy(self.Settings["URL"])
        self.daemon_thread = RTDaemon(RemoteUpdate.Jobs, wrtc.Proxy)
        self.daemon_thread.start()
        if sys.argv[1]:
            wrtc.AddTorrent(None, sys.argv[1])
        return True

    @classmethod
    def LoadIcons(cls):
        cls.Icons['play'] = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR)
        cls.Icons['pause'] = wx.ArtProvider.GetBitmap(wx.ART_CROSS_MARK, wx.ART_TOOLBAR)
        cls.Icons['add'] = wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR)
        cls.Icons['remove'] = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_FRAME_ICON)
        cls.ControlIcons = (wrtc.Icons['play'], wrtc.Icons['pause'])

    @classmethod
    def LoadSettings(cls):
        try:
            config_file = open(cls.ConfigPath)
            cls.Settings.update(pickle.load(config_file))
            config_file.close()
        except IOError, EOFError:
            NB.ChangeSelection(NB.GetPageCount()-1)

    @classmethod
    def SaveSettings(cls):
        try:
            config_file = open(cls.ConfigPath, "w+")
            pickle.dump(wrtc.Settings,config_file)
            config_file.close()
            print "Saved settings file", cls.ConfigPath
        except:
            print "Could not save settings file:", cls.ConfigPath

    @classmethod
    def AddTorrent(self,e=None,filename=None):
        dlg = LoadTorrentDialog()
        if filename:
            dlg.filepath.SetValue(filename)
        if dlg.ShowModal() == wx.ID_OK:
            if dlg.filepath.GetValue():
                self.SendTorrentFile(dlg.filepath.GetValue())
            elif dlg.url.GetValue():
                self.SendTorrentUrl(dlg.url.GetValue())
        dlg.Destroy()

    @classmethod
    def SendTorrentFile(self, filename, start=False):
        action = "load_raw"
        if start:
            action += "_start"
        torrent_file = open(filename,'rb')
        torrent_data = Binary(torrent_file.read()+torrent_file.read())
        torrent_file.close()
        RemoteUpdate.Jobs.put((action, torrent_data))

    @classmethod
    def SendTorrentUrl(self, url, start=False):
        action = "load"
        if start:
            action += "_start"
        RemoteUpdate.Jobs.put((action, url))


class MainWindow(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, size=(600,600))
        self.refresher_thread = UpdateScheduler()
        ToolBar = wx.BoxSizer(wx.HORIZONTAL)
        AddTorrentButton = wx.Button(self,label="Add torrent")
        AddTorrentButton.Bind(wx.EVT_BUTTON, wrtc.AddTorrent)
        ToolBar.Add(AddTorrentButton, 0, wx.RIGHT, 5)

        global NB
        NB = TorrentsNotebook(self)
        MainSizer = wx.BoxSizer(wx.VERTICAL)
        MainSizer.Add(ToolBar, 0, wx.TOP | wx.BOTTOM, 5)
        MainSizer.Add(NB, 1, wx.EXPAND)
        self.SetSizer(MainSizer)
        self.Show()
        self.refresher_thread.start()

    def OnExit(self,e):
        InitQueues()
        self.Destroy()


class TorrentsNotebook(wx.Notebook):
    def __init__(self, *args, **kwargs):
        wx.Notebook.__init__(self, *args, **kwargs)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChange)
        self.views_to_load = ["incomplete", "seeding", "stopped"]
        self.LoadViews()
        self.AddPage(SettingsPanel(self), 'Settings')

    def OnPageChange(self, event):
        page = self.GetPage(event.GetSelection())
        InitQueues()
        if page and hasattr(page, "torrents"):
            page.Synchronize()
        event.Skip()
        
    def LoadViews(self):
        self.DeleteAllPages()
        for view in self.views_to_load:
            self.AddPage(ViewPanel(self, view), view.capitalize());


class ViewPanel(sp.ScrolledPanel):
    def __init__(self, parent, title="default"):
        sp.ScrolledPanel.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.torrents = {}
        self.title = title
        self.SetSizer(sizer)
        self.Bind(wx.EVT_SCROLLWIN, self.OnScroll)

    def AddToView(self, hashlist):
        for infohash in hashlist:
            if infohash not in RemoteUpdate.JobCounter:
                RemoteUpdate.JobCounter.changecount(infohash)
            self.torrents[infohash] = TorrentPanel(self, infohash)
            self.GetSizer().Add(self.torrents[infohash], 0, wx.TOP | wx.BOTTOM | wx.EXPAND, 3)
        self.SetupScrolling()

    def RemoveFromView(self, hashlist):
        for infohash in hashlist:
            panel = self.torrents[infohash]
            del self.torrents[infohash]
            panel.Show(False)
            panel.Destroy()
        self.SetupScrolling()

    def OnScroll(self, event):
        event.Skip()
        InitQueues()



    def UpdateVisible(self):
        for child in self.GetChildren():
            child.Update()
      
    def Synchronize(self):
        RemoteUpdate.Jobs.put(("download_list",self.title, RemoteUpdate.CbHandler, cbec.CallbackEvent(method=getattr(self, "UpdateList"))))

    def UpdateList(self, new_hashlist):
        current_hashlist = self.torrents.keys()
        addList = [val for val in new_hashlist if val not in current_hashlist]
        rmList = [val for val in current_hashlist if val not in new_hashlist]
        if len(rmList):
            self.RemoveFromView(rmList)
        if len(addList):
            self.AddToView(addList)
        if len(current_hashlist) != len(self.torrents.keys()):
            self.GetSizer().Layout()

class TorrentPanel(wx.Panel):
    def __init__(self, parent, infohash):
        wx.Panel.__init__(self, parent, style=wx.RAISED_BORDER)
        self.infohash = infohash
        TopSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(TopSizer)
        InfoSizer = wx.BoxSizer(wx.VERTICAL)
        TopSizer.Add(InfoSizer, 1, wx.EXPAND | wx.ALL, 2)
        LnTSizer = wx.BoxSizer(wx.HORIZONTAL)
        RnPSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ProgressBar = RemoteProgressBar(self, self.infohash)
        self.UpRateLabel = RemoteLabel(self, infohash, "d.get_up_rate", "0", "Up: %s/s", FormatBytes, True)
        self.DownRateLabel = RemoteLabel(self, infohash, "d.get_down_rate", "0", "Down: %s/s", FormatBytes, True)
        RnPSizer.Add(self.ProgressBar, 1, wx.EXPAND)
        RnPSizer.Add(self.UpRateLabel, 0, wx.ALIGN_CENTER | wx.LEFT, 3)
        RnPSizer.Add(self.DownRateLabel, 0, wx.ALIGN_CENTER)
        self.TitleLabel = RemoteLabel(self, self.infohash, "d.get_base_filename", "Loading Torrent Info...")
        self.EraseButton = wx.BitmapButton(self, wx.ID_ANY, wrtc.Icons['remove'])
        self.EraseButton.Bind(wx.EVT_BUTTON, self.OnErase)
        LnTSizer.Add(self.TitleLabel, 1, wx.EXPAND | wx.CENTRE | wx.TOP | wx.BOTTOM, 3)
        LnTSizer.Add(self.EraseButton, 0, wx.ALIGN_RIGHT | wx.ALL, 2)
        InfoSizer.Add(LnTSizer, 0, wx.EXPAND)
        InfoSizer.Add(RnPSizer, 0, wx.EXPAND)
        self.PlayPause = StateButton(self, self.infohash, wrtc.Icons['pause'])
        TopSizer.Prepend(self.PlayPause, 0, wx.ALIGN_CENTER | wx.ALL, 2)
        self.Update()

    def Update(self):
        if self.TitleLabel.GetLabel() == "Loading Torrent Info...":
            self.TitleLabel.UpdateSelf("label")
        self.PlayPause.UpdateSelf("bitmap")
        self.UpRateLabel.UpdateSelf("label")
        if not self.ProgressBar.GetRange():
            self.ProgressBar.UpdateSelf("range")
        if not self.IsComplete():
            self.DownRateLabel.UpdateSelf("label")
            self.ProgressBar.UpdateSelf("value")

    def IsComplete(self):
        v = self.ProgressBar.GetValue()
        r = self.ProgressBar.GetRange()
        if r > 0 and v == r:
            return True
        return False

    def Start(self):
        RemoteUpdate.Jobs.put(("d.start",self.infohash))

    def Stop(self):
        RemoteUpdate.Jobs.put(("d.stop",self.infohash))

    def OnErase(self, e):
        dlg = wx.MessageDialog(self, "Are you sure you want to remove this torrent?", "Delete torrent", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_OK:
            RemoteUpdate.Jobs.put(("d.erase",self.infohash))
            sizer = self.GetParent().GetSizer()
            self.Destroy()
            sizer.Layout()
        dlg.Destroy()

class UpdateScheduler(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)
    
    def run(self):
        while True:
            NB.GetCurrentPage().UpdateVisible()
            NB.GetCurrentPage().Synchronize()
            time.sleep(2)

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
        if wrtc.Settings["REMOTE_BROWSE_ENABLE"]:
            dest_browse_button = wx.Button(self, 99, "Browse...")
            dest_sizer.Add(dest_browse_button, 0, wx.ALL, padding)
              
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
        """ Open a file"""
        dlg = wx.FileDialog(self, "Choose a file", os.getcwd(), "", "*.torrent", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            self.filepath.SetValue(self.dirname+"/"+self.filename)
        dlg.Destroy()


class SettingsPanel(sp.ScrolledPanel):
    def __init__(self, parent):
        sp.ScrolledPanel.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        padding = 3
        settings = {}
        for k, v in wrtc.Settings.iteritems():
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
        save.Bind(wx.EVT_BUTTON, self.SaveSettings)
        sizer.Add(save, 0, wx.ALIGN_RIGHT | wx.ALL, padding)

    def SaveSettings(self, evt):
        for k, v in self.settings.iteritems():
            wrtc.Settings[k] = v['ctrl'].GetValue()
        wrtc.SaveSettings()
        

    """ This is a NOP because the GUI updater attempts to update the settings page"""
    def UpdateVisible(self):
        return True

    """ This is a NOP because the GUI updater attempts to update the settings page"""
    Synchronize = UpdateVisible

def InitQueues():
    try:
        RemoteUpdate.Jobs.mutex.acquire()
        RemoteUpdate.Jobs.queue.clear()
        RemoteUpdate.Jobs.mutex.release()
    except:
        print("Ah fuck")
        time.sleep(10)
        quit()
    RemoteUpdate.JobCounter.__init__()

def FormatBytes(bytes, characters=5):
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

RemoteUpdate.CbHandler = cbec.CallbackEventCatcher("infohash",getattr(RemoteUpdate.JobCounter, 'dec'))

app = wrtc()

RemoteUpdate.Icons = wrtc.Icons
RemoteUpdate.ControlIcons = wrtc.ControlIcons

app.MainLoop()
