import wx
from multiqueue import MultiQueue
from Queue import Queue
from callbackeventcatcher import CallbackEvent

class RemoteUpdate:
    ''' Base class for controls that update their value via xmlrpc calls '''
    def __init__(self, parent, attributes, view):
        parent.queue_setup(self)
        self.view = view
        self.attributes = attributes
        self.waiting = False
        self.skip = False

    def update_self(self, attribute):
        a = self.attributes[attribute]
        if self.IsVisible() and not self.waiting and not self.skip:
            self.waiting = True
            self.job_queue.put(( a["command"], self.infohash,
                             CallbackEvent(method=getattr(self, a["callback"]))
                          ))
            self.job_counter.inc(self.infohash)

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
    def __init__(self, parent):
        wx.Gauge.__init__(self, parent, wx.ID_ANY, 0)
        self.infohash = parent.infohash
        attributes = {
            "range": {
                "command": "d.get_size_bytes", 
                "callback": "SetRange" },
            "value": {
                "command": "d.get_bytes_done",
                "callback": "SetValue",
            }
        }
        RemoteUpdate.__init__(self, parent, attributes, self.GetGrandParent())

    def SetValue(self, pos):
        wx.Gauge.SetValue(self, pos)
        if pos == self.GetRange():
            self.skip = True

class RemoteLabel(wx.StaticText, RemoteUpdate):
    def __init__(self, parent, command, default, format_string="%s", transformer=lambda s:str(s), dynamic=False):
        wx.StaticText.__init__(self, parent, wx.ID_ANY, format_string % transformer(default))
        self.infohash = parent.infohash
        self.command = command
        self.format_string = format_string
        self.transformer = transformer
        self.dynamic = dynamic
        attributes = {"label": {
            "command": command, 
            "callback": "SetLabel" }}
        RemoteUpdate.__init__(self, parent, attributes, self.GetGrandParent())

    def SetLabel(self, value=None):
        wx.StaticText.SetLabel(self, self.format_string % self.transformer(value))
        if not self.dynamic and value != "":
            self.skip = True

class StateButton(wx.BitmapButton, RemoteUpdate):
    def __init__(self, parent, bind_to, bitmap):
        wx.BitmapButton.__init__(self, parent, wx.ID_ANY, bitmap[0])
        self.icons = bitmap
        self.Bind(wx.EVT_BUTTON, self.OnClick)
        self.infohash = parent.infohash
        self.action = bind_to
        attributes = {
            "bitmap": {
                "command": "d.get_state", 
                "callback": "SetBitmap" 
            }
        }
        RemoteUpdate.__init__(self, parent, attributes, self.GetGrandParent())

    def SetBitmap(self, value):
        self.SetBitmapLabel(self.icons[value])
        self.Enable()

    def OnClick(self, event):
        self.Disable()
        self.action(self) # Action expects the button as first argument
        self.update_self("bitmap")
