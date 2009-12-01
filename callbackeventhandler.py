import wx
from wx.lib import newevent as ne
(CallbackEvent, EVT_REMOTE_CALLBACK) = wx.lib.newevent.NewEvent()
class CallbackEventHandler(wx.EvtHandler):
    def __init__(self, special_key, dec_function):
        wx.EvtHandler.__init__(self)
        self.Bind(EVT_REMOTE_CALLBACK, self.HandleEvent)
        self.dec_function = dec_function
        self.special_key = special_key

    def HandleEvent(self, event):
        ''' calls event.method(event.response) so that controls can put their 
        own update callbacks into the job queue '''
        if self.special_key in event.method.im_self.GetParent().__dict__.keys():
            self.dec_function(event.method.im_self.GetParent().__dict__[self.special_key])
            event.method.im_self.waiting -= 1
        event.method(event.response)
