import wx
from multiqueue import MultiQueue
from Queue import Queue
from callbackeventcatcher import CallbackEvent

class RemoteUpdate:
    JobCounter = MultiQueue()
    Jobs = Queue()
    def __init__(self, attributes, view):
        self.view = view
        self.attributes = attributes
        self.waiting = False
        self.skip = False

    def UpdateSelf(self, attribute):
        a = self.attributes[attribute]
        if self.IsVisible() and not self.waiting and not self.skip:
            self.waiting = True
            self.Jobs.put((a["command"],a["parameter"], self.CbHandler, CallbackEvent(method=getattr(self, a["callback"]))))
            self.JobCounter.inc(a["parameter"])

    def IsVisible(self):
        if self.view == self.view.GetParent().GetCurrentPage():
            panel = self.GetParent()
            rect = self.GetRect()
            
            scrollpos = [self.view.GetScrollPos(wx.HORIZONTAL), self.view.GetScrollPos(wx.VERTICAL)]
            ppu = self.view.GetScrollPixelsPerUnit()
            scrollpos[0] *= ppu[0]
            scrollpos[1] *= ppu[1]
            rect.Offset((scrollpos[0], scrollpos[1]))
            rect.Offset(self.view.GetPosition())
            rect.Offset(panel.GetPosition())
            if self.view.GetRect().Intersects(rect):
                return True
        return False

class RemoteProgressBar(wx.Gauge, RemoteUpdate):
    def __init__(self, parent, infohash):
        wx.Gauge.__init__(self, parent, wx.ID_ANY, 0)
        attributes = {
            "range": {
                "command": "d.get_size_bytes", 
                "parameter": infohash, 
                "callback": "SetRange" },
            "value": {
                "command": "d.get_bytes_done",
                "parameter": infohash,
                "callback": "SetValue",
            }
        }
        self.infohash = infohash
        RemoteUpdate.__init__(self, attributes, self.GetGrandParent())

    def SetValue(self, pos):
        wx.Gauge.SetValue(self, pos)
        if pos == self.GetRange():
            self.skip = True


class RemoteLabel(wx.StaticText, RemoteUpdate):
    def __init__(self, parent, infohash, command, default, format_string="%s", transformer=lambda s:str(s), dynamic=False):
        wx.StaticText.__init__(self, parent, wx.ID_ANY, format_string % transformer(default))
        self.infohash = infohash
        self.command = command
        self.format_string = format_string
        self.transformer = transformer
        self.dynamic = dynamic
        attributes = {"label": {
            "command": command, 
            "parameter": infohash, 
            "callback": "SetLabel" }}
        RemoteUpdate.__init__(self, attributes, self.GetGrandParent())

    def SetLabel(self, value=None):
        wx.StaticText.SetLabel(self, self.format_string % self.transformer(value))
        if not self.dynamic and value != "":
            self.skip = True

class StateButton(wx.BitmapButton, RemoteUpdate):
    def __init__(self, parent, infohash, bitmap):
        wx.BitmapButton.__init__(self, parent, wx.ID_ANY, bitmap)
        self.Bind(wx.EVT_BUTTON, self.OnClick)
        self.infohash = infohash
        attributes = {
            "bitmap": {
                "command": "d.get_state", 
                "parameter": infohash, 
                "callback": "SetBitmap" 
            }
        }
        RemoteUpdate.__init__(self, attributes, self.GetGrandParent())

    def SetBitmap(self, value):
        self.SetBitmapLabel(self.ControlIcons[value])
        self.Enable()

    def OnClick(self, event):
        self.Disable()
        if self.GetBitmapLabel() == self.ControlIcons[0]:
            self.GetParent().Start()
            self.UpdateSelf("bitmap")
        elif self.GetBitmapLabel() == self.ControlIcons[1]:
            self.GetParent().Stop()
            self.UpdateSelf("bitmap")
