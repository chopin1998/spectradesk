import os
import subprocess
import sys


def test_auto_updates_display_and_dialog_follows_theme(tmp_path):
    script='''
from argparse import Namespace
from PySide6 import QtCore,QtGui,QtWidgets as W
from spectradesk.app import Window
app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'));win.show()
errors=[];phase=0
def poll():
    global phase
    try:
        if not win.ready:return
        if phase==0:
            assert win.connect_button.objectName()=='disconnect'
            win.integration.setValue(333)
            assert win.integration_label.text()=='积分时间 · 333'
            win.request_auto();phase=1;return
        if win.auto_busy:return
        assert win.integration.value()==48
        assert win.integration.text()=='48'
        assert win.integration_label.text()=='积分时间 · 48'
        assert win.integration.isEnabled()
        store=QtCore.QSettings('SpectraDesk','SpectraDesk')
        assert store.value('integration',type=int)==48
        for index,base,text in ((2,'#18212c','#dce4ed'),(1,'#ffffff','#263349')):
            win.theme.setCurrentIndex(index)
            dialog=win.create_save_dialog();dialog.show();app.processEvents()
            assert dialog.testOption(W.QFileDialog.Option.DontUseNativeDialog)
            edit=dialog.findChild(W.QLineEdit,'fileNameEdit')
            assert edit is not None
            assert edit.palette().color(QtGui.QPalette.ColorRole.Base).name()==base
            assert edit.palette().color(QtGui.QPalette.ColorRole.Text).name()==text
            assert edit.palette().color(QtGui.QPalette.ColorRole.HighlightedText).name()=='#ffffff'
            tree=dialog.findChild(W.QTreeView,'treeView')
            assert tree is not None
            assert tree.palette().color(QtGui.QPalette.ColorRole.Text).name()==text
            dialog.reject();dialog.deleteLater()
        win.set_controls(False)
        assert win.connect_button.objectName()=='connect'
        assert win.connect_button.text()=='连接光谱仪'
        timer.stop();win.close();app.quit()
    except BaseException as error:
        errors.append(error);timer.stop();win.close();app.quit()
timer=QtCore.QTimer();timer.timeout.connect(poll);timer.start(40)
app.exec()
if errors:raise errors[0]
assert phase==1
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
