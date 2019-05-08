#!/usr/bin/env python

import os
import re
import sys
import wx

try:
  from agw import hypertreelist as HTL
except ImportError:
  import wx.lib.agw.hypertreelist as HTL

from collections import namedtuple


class DirectoryObject(object):
  def __init__(self, name, rootdir, dirs, files):
    self.name = os.path.basename(name)
    self.rootdir = rootdir
    self.files = files
    self.dirs = dict()
    for name in dirs:
      self.dirs[name] = list()

  def walk(self):
    objs = []

    def _walk(listp, item):
      listp.append(item)
      for _, objd in item.dirs.items():
        if isinstance(objd, DirectoryObject):
          _walk(listp, objd)

    _walk(objs, self)
    for obj in objs:
      yield obj.rootdir, obj.dirs.keys(), obj.files

  def listdir(self):
    return self.files + self.dirs.keys()

  @staticmethod
  def listDir(dirname):
    info = dict()
    for rootdir, dirs, files in os.walk(dirname):
      name = rootdir.replace(dirname, '').lstrip('/')
      info[name] = DirectoryObject(name, rootdir, dirs, files)

    def updateRecursively(root, item):
      if item:
        for name in item.dirs.keys():
          dname = os.path.join(root, name)
          if dname in info:
            item.dirs[name] = info[dname]
            updateRecursively(dname, item.dirs[name])

      return item

    return updateRecursively('', info.get(''))


class FileWorker(object):
  class FileItem(object):
    def __init__(self, filename, linkto=None):
      self.filename = filename
      self.linkto = linkto
      self.dirname = os.path.dirname(filename)
      self.sincerity = self.name = os.path.basename(filename)

      self.cousins = list()

    def __repr__(self):
      ret = 'name: ' + self.name + ', fullname: ' + self.filename
      if self.linkto:
        ret += ', linkto: ' + self.linkto
      ret += ', dir:' + self.dirname
      if self.cousins:
        ret += ', cousins: [%s]' % ','.join([f.name for f in self.cousins])
      if self.sincerity != self.name:
        ret += ', sincerity: ' + self.sincerity

      return ret

  def __init__(self, objdir):
    self.cousins = dict()
    self.similarities = dict()

    self.files = dict()
    for root, dirs, files in objdir.walk():
      for fname in files:
        item = self.aggregate(
          root, self.similarities, self.cousins,
          os.path.join(root, fname).replace(objdir.rootdir, '').lstrip('/'))

        if fname not in self.files:
          self.files[fname] = list()

        self.files[fname].append(item)

    #print 'CU:', self.cousins
    #print 'SIMILAR:', self.similarities

  def get(self, name):
    return self.files.get(name), self.cousins.get(name), self.similarities.get(name)

  @staticmethod
  def aggregate(rootdir, similarities, cousins, name):
    """rootdir is the file directory, name is relative to "root", not rootdir."""
    fullname = os.path.join(rootdir, os.path.basename(name))
    fi = FileWorker.FileItem(name,
      linkto=os.readlink(fullname) if os.path.islink(fullname) else None)

    # try analyzing file name with names
    if fi.name.find('.so') > 0:
      name = fi.name
      while True:
        rindex = name.rfind('.')
        if rindex == -1:
          rindex = name.rfind('-')

        if rindex != -1:
          suffix = name[rindex + 1:]
          if suffix == 'so' or re.match(r'^\d+$', suffix):
            name = name[:rindex]
            continue

        if name != fi.name:
          if not name.endswith('.so'):
            name += '.so'

          if os.path.lexists(os.path.join(os.path.dirname(fullname), name)):
            fi.sincerity = name

        break

    if fi.name not in similarities:
      similarities[fi.name] = list()
    similarities[fi.name].append(fi)

    if fi.sincerity != fi.name and fi.sincerity in similarities:
      similarities[fi.sincerity].append(fi)

    if fi.name not in cousins:
      cousins[fi.name] = list()
    cousins[fi.name].append(fi)

    return fi


class DirSelectionDialog(wx.Dialog):
  def __init__(self, parent, title):
    wx.Dialog.__init__(self, parent, -1, title)

    v_sizer = wx.BoxSizer(wx.VERTICAL)

    sizer = wx.FlexGridSizer(2, 3, 2, 2)
    sizer.AddGrowableCol(1)

    sizer.Add(wx.StaticText(self, -1, "Target Dir"), 0)
    self.dir = wx.TextCtrl(self, -1, size=(200, -1))
    self.dir.Enable(False)
    sizer.Add(self.dir, 1, wx.EXPAND | wx.ALL)
    self.bdir = wx.Button(self, -1, "...", size=(30, -1))
    sizer.Add(self.bdir, 1)

    sizer.Add(wx.StaticText(self, -1, "Referred Dir"), 0)
    self.refer = wx.TextCtrl(self, -1, size=(200, -1))
    self.refer.Enable(False)
    sizer.Add(self.refer, 1, wx.EXPAND | wx.ALL)
    self.brefer = wx.Button(self, -1, "...", size=(30, -1))
    sizer.Add(self.brefer, 1)

    v_sizer.Add(sizer, 0, wx.EXPAND | wx.ALL)

    line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
    v_sizer.Add(line, 0, wx.GROW | wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

    v_sizer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL),
                0, wx.ALL | wx.ALIGN_RIGHT, 2)

    wx.EVT_BUTTON(self, self.bdir.GetId(), self.OnEventDirSelection)
    wx.EVT_BUTTON(self, self.brefer.GetId(), self.OnEventDirSelection)

    self.SetSizer(v_sizer)
    self.Layout()
    self.Fit()

  def OnEventDirSelection(self, event):
    dialog = wx.DirDialog(
      self, 'Select a directory', style=wx.DD_DEFAULT_STYLE)

    if dialog.ShowModal() == wx.ID_OK:
      if event.GetId() == self.bdir.GetId():
        self.dir.WriteText(dialog.GetPath())
      else:
        self.refer.WriteText(dialog.GetPath())

    dialog.Destroy()

  def GetPaths(self):
    return self.dir.GetValue(), self.refer.GetValue()


class DirDiffFrame(wx.Frame):
  def __init__(self, parent, title, *args):
    wx.Frame.__init__(self, parent, -1, title)

    mb = wx.MenuBar()
    menu = wx.Menu()
    menu.Append(wx.ID_FILE, "&Open directrories ...")
    menu.Append(wx.ID_EXIT, "E&xit")
    mb.Append(menu, "&File")
    self.SetMenuBar(mb)

    wx.EVT_MENU(self, wx.ID_FILE, self.OnCmd_File)
    wx.EVT_MENU(self, wx.ID_EXIT, self.OnCmd_Exit)

    self.tree = HTL.HyperTreeList(self, agwStyle=wx.TR_HAS_BUTTONS | wx.TR_HAS_VARIABLE_ROW_HEIGHT)
    if len(args) > 0 and len(args[0]) > 1:
      wx.CallAfter(self.UpdateView, args[0][0], args[0][1])

  def UpdateView(self, origin, refer):
    # TODO: clean tree
    self.tree.AddColumn('Mixed')
    self.tree.AddColumn('LR')
    self.tree.AddColumn('Comment')

    obja = DirectoryObject.listDir(origin)
    worka = FileWorker(obja)
    objb = DirectoryObject.listDir(refer)
    workb = FileWorker(objb)

    def listdir(dirname):
      if dirname and os.path.exists(dirname):
        return os.listdir(dirname)
      else:
        return []

    def UpdateTree(tree, lroot, left, objL, rroot, right, objR):
      dira = (objL and objL.listdir()) or []
      dirb = (objR and objR.listdir()) or []

      for item in sorted(list(set(dira + dirb))):
        child = self.tree.AppendItem(tree, item)

        fa = os.path.join(left, item)
        fb = os.path.join(right, item)

        alls, flag, excluded = [], '', [item]

        if objL:
          excluded.append(os.path.join(objL.name, item))
        if objR:
          excluded.append(os.path.join(objR.name, item))

        if os.path.lexists(fa):
          flag += 'L'
          files, _, _ = worka.get(item)
          if files:
            alls.extend(['@' + f.linkto for f in files if f.linkto])

        if os.path.lexists(fb):
          flag += 'R'
          excluded.append(os.path.join(objR.name, item))
          files, _, _ = workb.get(item)
          if files:
            alls.extend(['@' + f.linkto for f in files if f.linkto])

        self.tree.SetItemText(child, flag, 1)
        if os.path.isdir(fa) or os.path.isdir(fb):
          UpdateTree(
            child,
            lroot, fa, objL and objL.dirs.get(item),
            rroot, fb, objR and objR.dirs.get(item))
        elif len(flag) == 1:
          if flag == 'L':
            worker = workb
            excluded.append(fb[len(rroot):])
          else:
            worker = worka
            excluded.append(fa[len(lroot):])

          files, cousins, sincerity = worker.get(item)
          if files:
            for f in files:
              if f.sincerity:
                alls.append(f.sincerity)
              if f.linkto:
                alls.append('@' + f.linkto)
          if cousins:
            alls.extend([f.filename for f in cousins])
          if sincerity:
            alls.extend([f.filename for f in sincerity])

          if len(alls):
            self.tree.SetItemText(
              child, ', '.join(set(alls) - set(excluded)), 2)

    UpdateTree(
      self.tree.AddRoot(origin), origin, origin, obja, refer, refer, objb)

  def OnCmd_File(self, event):
    dialog = DirSelectionDialog(self, "Set directories")
    if dialog.ShowModal() == wx.ID_OK:
      origin, refer = dialog.GetPaths()

      self.UpdateView(origin, refer)

  def OnCmd_Exit(self, event):
    self.Destroy()


class DirDiffApp(wx.App):
  def __init__(self, *args):
    self.args = args

    wx.App.__init__(self, 0)

  def OnInit(self):
    frame = DirDiffFrame(None, 'Dir-Diff', *self.args)
    self.SetTopWindow(frame)
    frame.Show(True)

    return True

if __name__ == '__main__':
  app = DirDiffApp(sys.argv[1:])
  app.MainLoop()
