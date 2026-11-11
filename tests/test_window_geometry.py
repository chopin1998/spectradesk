import os
import subprocess
import sys


def test_geometry_saved_and_restored_by_application(tmp_path):
    script="""
from argparse import Namespace
from PySide6 import QtCore,QtWidgets as W
from spectradesk.app import Window
app=W.QApplication([])
args=Namespace(demo=True,connect=False,smoke=None,renderer='raster')
first=Window(args)
first.resize(1240,780);first.move(20,25)
first.setWindowState(QtCore.Qt.WindowState.WindowMaximized)
expected=first.saveGeometry();first.close()
store=QtCore.QSettings('SpectraDesk','SpectraDesk')
assert store.value('window/geometry')==expected
calls=[]
class ObservedWindow(Window):
    def restoreGeometry(self,geometry):
        calls.append(geometry)
        return super().restoreGeometry(geometry)
second=ObservedWindow(args)
assert calls==[expected]
assert second.isMaximized()
second.close()
# Corrupt/incompatible stored data must not prevent startup.
store.setValue('window/geometry',QtCore.QByteArray(b'invalid'));store.sync()
third=Window(args);assert third.width()>=third.minimumWidth();third.close()
"""
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
