import os,sys,subprocess

def test_close_during_capture_and_pending_band_refresh(tmp_path):
    script='''
import sys
from argparse import Namespace
from PySide6 import QtCore,QtWidgets as W,QtTest
from spectradesk.app import Window
from spectradesk.workbench import Workbench
app=W.QApplication([]);app.setQuitOnLastWindowClosed(False)
errors=[];sys.excepthook=lambda kind,value,tb:errors.append(str(value))
for scenario in ('startup','standalone','workbench'):
 options=Namespace(demo=True,smoke=None,renderer='raster',backend='camera')
 win=Workbench(options) if scenario=='workbench' else Window(options)
 win.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose);win.show()
 QtTest.QTest.qWait(20 if scenario=='startup' else 400)
 targets=win.sessions if scenario=='workbench' else [win]
 if scenario!='startup':
  for target in targets:target.start(True)
  QtTest.QTest.qWait(150)
 for target in targets:
  QtCore.QTimer.singleShot(0,target.align_raw_band)
 win.close()
 QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
 QtTest.QTest.qWait(200)
assert not errors,errors
'''
    result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path)),capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'already deleted' not in result.stderr
    assert 'PeakPropertyWarning' not in result.stderr
