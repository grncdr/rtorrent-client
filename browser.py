import wx
class PathBrowser(wx.TreeCtrl):
    def __init__(self, parent):
    def get_dirs(root):
        command = 'execute_capture'
        args = ['find',root,'-maxdepth','1','-type','d','-readable']
        job_queue.put((command, args, munge_dirs))

    def munge_dirs(output)
        root = output.split('\n').pop(0)
        return output.replace(root,'').split('\n')[1:-1] 
