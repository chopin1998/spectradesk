import os,sys,subprocess

def test_ui_limits_restore_old_settings_and_auto_update(tmp_path):
    code="""
from argparse import Namespace
from PySide6 import QtCore,QtWidgets as W
from spectradesk.app import Window
app=W.QApplication([])
store=QtCore.QSettings('SpectraDesk','SpectraDesk');store.setValue('average',64);store.setValue('smooth',50);store.sync()
win=Window(Namespace(demo=True,smoke=None,renderer='raster'))
try:
 assert win.average.maximum()==8 and win.average.value()==8
 assert win.smooth.maximum()==8 and win.smooth.value()==8
 win.update_average(1);win.on_auto(100,'test')
 assert win.average.value()==1
 assert win.settings_store().value('average',type=int)==1
finally:win.close()
"""
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path)),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
