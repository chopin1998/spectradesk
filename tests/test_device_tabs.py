import os,sys,subprocess

def test_single_device_navigation_and_theme_status(tmp_path):
    code='''
from argparse import Namespace
from PySide6 import QtWidgets as W,QtTest
from spectradesk.workbench import Workbench
app=W.QApplication([]);w=Workbench(Namespace(demo=True,smoke=None,renderer='raster'));w.show()
try:
 for _ in range(100):
  if all(s.ready for s in w.sessions):break
  QtTest.QTest.qWait(20)
 w.timer.stop();a,b=w.sessions
 assert all(s.ready for s in w.sessions)
 w.tabs.setCurrentIndex(2);a.busy=True;w.device_tab_event(0,'连续采集中');QtTest.QTest.qWait(130)
 assert w.tabs.currentIndex()==0
 assert '采集中' in w.tabs.tabToolTip(0) and '可用' in w.tabs.tabToolTip(1)
 # A manual tab selection must not be stolen on subsequent refreshes.
 w.tabs.setCurrentIndex(2);w.update_tab_states();QtTest.QTest.qWait(130);assert w.tabs.currentIndex()==2
 b.busy=True;w.device_tab_event(1,'连续采集中');QtTest.QTest.qWait(130);assert w.tabs.currentIndex()==2
 a.busy=False;w.update_tab_states();QtTest.QTest.qWait(130);assert w.tabs.currentIndex()==1
 before=w.tabs.tabBar().tabTextColor(1);w.sessions[0].theme.setCurrentIndex(2)
 assert w.tabs.tabBar().tabTextColor(1)!=before
 b.busy=False;b.ready=False;b.device_present=False;b.device_status.setText('连接异常');w.update_tab_states();assert '异常' in w.tabs.tabToolTip(1)
 # A fast single capture may finish before the delayed navigation callback.
 a.busy=False;w.tabs.setCurrentIndex(3);w.device_tab_event(0,'单次采集中');QtTest.QTest.qWait(130);assert w.tabs.currentIndex()==0
finally:w.close()
'''
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path)),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
