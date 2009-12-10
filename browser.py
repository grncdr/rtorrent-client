import wx
class PathBrowser(wx.TreeCtrl):
    def __init__(self, parent, remote_root):
        wx.TreeCtrl.__init__(self, parent, size=(-1,200))
        self.daemon = wx.GetApp().daemon
        self.remote_root = remote_root
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self._on_expand)
        self._load_root()

    def _on_expand(self, evt):
        node = evt.GetItem()
        if not self.GetPyData(node)['loaded']:
            self._load_children(node)
        evt.Skip()

    def _load_root(self):
        self.root_node = self.AddRoot('Root')
        self.SetPyData(self.root_node, {'path': self.remote_root, 'loaded': False})
        self._load_children(self.root_node)

    def _load_children(self, node):
        self.SetItemText(node, self.GetItemText(node) + ' [loading...]')
        command = 'execute_capture'
        args = ['find', self.GetPyData(node)['path'], '-maxdepth','1','-type','d','-readable']
        self.daemon.put((command, args, self._make_callback(node)))

    def _make_callback(self, node):
        def callback(output):
            data = self.GetPyData(node)
            data['loaded'] = True
            self.SetItemText(node, self.GetItemText(node).replace(' [loading...]',''))
            self.SetPyData(node, data)
            for dir in output.split('\n')[1:-1]:
                child = self.AppendItem(node, dir.replace(data['path'],'').replace('/',''))
                self.SetItemHasChildren(child, True)
                self.SetPyData(child, {'path': dir, 'loaded': False})
            self.Expand(node)
        return callback

