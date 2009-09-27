class RemoteUpdate:
    JobCounter = MultiQueue()
    jobs = Queue()
    def __init__(self, attributes, callback_handler, put_job, inc_job):
        self.CbHandler = callback_handler
				self.put_job = put_job
				self.inc_job = inc_job
        self.attributes = attributes
        self.waiting = False
        self.skip = False

    def UpdateSelf(self, attribute):
        a = self.attributes[attribute]
        if self.IsVisible() and not self.waiting and not self.skip:
            self.waiting = True
            self.put_job((a["command"],a["parameter"], self.CbHandler, cbec.CallbackEvent(method=getattr(self, a["callback"]))))
            self.inc_job(a["parameter"])

    def IsVisible(self):
        view = self.GetParent()
        while type(view) != type(NB.GetCurrentPage()):
            view = parent.GetParent()
        if view == NB.GetCurrentPage():
            panel = self.GetParent()
            rect = self.GetRect()
            
            scrollpos = [view.GetScrollPos(wx.HORIZONTAL), view.GetScrollPos(wx.VERTICAL)]
            ppu = view.GetScrollPixelsPerUnit()
            scrollpos[0] *= ppu[0]
            scrollpos[1] *= ppu[1]
            rect.Offset((scrollpos[0], scrollpos[1]))
            rect.Offset(view.GetPosition())
            rect.Offset(panel.GetPosition())
            if view.GetRect().Intersects(rect):
                return True
        return False

class RemoteProgressBar(wx.Gauge, RemoteUpdate):
    def __init__(self, parent, infohash, *args, **kwargs):
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
        RemoteUpdate.__init__(self, attributes, *args, **kwargs)

    def SetValue(self, pos):
        wx.Gauge.__init__(self, pos)
        if pos == self.GetRange():
            self.skip = True

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
        RemoteUpdate.__init__(self, attributes, *args, **kwargs)

    def SetLabel(self, value=None):
        wx.StaticText.SetLabel(self, self.format_string % self.transformer(value))
        if not self.dynamic:
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
1       }
        RemoteUpdate.__init__(self, attributes, *args, **kwargs)

    def SetBitmap(self, value):
        self.SetBitmapLabel(wrtc.ControlIcons[value])
        self.Enable()

    def OnClick(self, event):
        self.Disable()
        if self.GetBitmapLabel() == wrtc.ControlIcons[0]:
            self.GetParent().Start()
            self.UpdateSelf("bitmap")
        elif self.GetBitmapLabel() == wrtc.ControlIcons[1]:
            self.GetParent().Stop()
            self.UpdateSelf("bitmap")

