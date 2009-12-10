from __future__ import with_statement
from ConfigParser import ConfigParser
import os, wx
class SettingsManager():
    ''' Wraps a ConfigParser and shows a nice little dialog  '''
    def __init__(self, filename, defaults={}):
        self.cfg = ConfigParser(defaults)
        self.filename = filename
        self.config_path = self.get_config_path()
        self.cfg.read(self.config_path)

    def get(self, *args):
        if not args: return None
        if len(args) > 1: return self.cfg.get(*args)
        return self.cfg.get("DEFAULT", args[0])

    def get_config_path(self):
        if os.name == 'nt':
            return os.path.expanduser("~/AppData/Local/%s" % self.filename)
        else:
            return os.path.expanduser("~/.config/%s" % self.filename)

    def show_dialog(self, evt=None):
        self.dlg = wx.Dialog(None, title="Settings")
        sizer = wx.FlexGridSizer(4,2,0,10)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)
        sizer.AddGrowableCol(1)
        self.dlg.SetSizer(sizer)
        self.controls = [] 
        for item in self.cfg.items("DEFAULT"):
            k, v = item
            control = wx.TextCtrl(self.dlg, value=v)
            label = wx.StaticText(self.dlg, label=k.title())
            self.controls.append((k, control,))
            sizer.Add(label, flag=wx.EXPAND|wx.ALL, border=10)
            sizer.Add(control, flag=wx.EXPAND|wx.ALL, border=10)
        save_button = wx.Button(self.dlg, id=wx.ID_OK, label="Save")
        save_button.Bind(wx.EVT_BUTTON, self.save)
        cancel = wx.Button(self.dlg, id=wx.ID_CANCEL)
        sizer.Add(cancel, 0, wx.ALIGN_LEFT | wx.ALL, border=10)
        sizer.Add(save_button, 0, wx.ALIGN_RIGHT | wx.ALL, border=10)
        self.dlg.ShowModal()

    def save(self, evt):
        for setting, control in self.controls:
            self.cfg.set("DEFAULT", setting, str(control.GetValue()))
        with open(self.config_path,'wb') as fh:
            self.cfg.write(fh)
        wx.GetApp().daemon.open(self.cfg.get("DEFAULT",'rTorrent URL'))
        self.dlg.Close()
