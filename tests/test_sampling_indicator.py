import os
import subprocess
import sys


def run_ui(script,tmp_path):
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_indicator_threshold_cycle_and_reset(tmp_path):
    run_ui('''
from types import SimpleNamespace
from PySide6 import QtWidgets as W
from spectradesk import sampling_indicator as module
app=W.QApplication([])
clock=[10.]
module.time=SimpleNamespace(monotonic=lambda:clock[0])
indicator=module.SamplingIndicator()
indicator.begin(10.)
assert indicator.isHidden()
clock[0]=10.21;indicator.tick()
assert not indicator.isHidden()
indicator.complete(.2)
assert indicator.isHidden() and not indicator.timer.isActive()
indicator.complete(2.)
indicator.begin(11.)
clock[0]=11.5
assert abs(indicator.phase()-.25)<1e-9
clock[0]=12.
assert abs(indicator.phase()-.5)<1e-9
clock[0]=13.
assert abs(indicator.phase())<1e-9
assert not indicator.isHidden()
indicator.begin(13.,reset=True)
assert indicator.period is None and indicator.isHidden()
indicator.complete(.1)
assert indicator.isHidden()
indicator.stop()
assert not indicator.active and not indicator.timer.isActive()
''',tmp_path)


def test_slow_sampling_animates_then_fast_sampling_shows_rate(tmp_path):
    run_ui('''
import time
from argparse import Namespace
import numpy as np
from PySide6 import QtCore,QtWidgets as W
from spectradesk import worker as module
from spectradesk.app import Window
class FakeDevice:
    duration=.4;parameter=250
    @classmethod
    def device_available(cls):return True
    def open(self):return dict(model='FLA5000',serial='timing',firmware='VER7.1',anchors=[]),np.linspace(300,900,2048),np.zeros(2048)
    def set_parameter(self,p):self.parameter=p
    def check_connected(self):pass
    def capture(self,average):
        time.sleep(self.duration)
        return np.full((average,2048),30000,dtype=np.uint16)
    def close(self):pass
module.Driver=FakeDevice
app=W.QApplication([])
win=Window(Namespace(demo=False,connect=False,smoke=None,renderer='raster'));win.show();win.average.setValue(1)
phase=0;ticks=0;errors=[];animated=False
def poll():
    global phase,ticks,animated
    ticks+=1
    try:
        if phase==0 and win.ready:
            win.start(True);phase=1
        elif phase==1 and win.frame_data is not None and win.frame_data['index']>=2:
            assert win.sampling_indicator.isVisible()
            assert 'Hz' not in win.measure_status.text()
            assert win.sampling_indicator.timer.isActive()
            assert ticks>10 # The UI kept processing events during blocking reads.
            animated=True
            win.worker.driver.duration=.05;phase=2
        elif phase==2 and 'Hz' in win.measure_status.text():
            assert win.sampling_indicator.isHidden()
            assert not win.measure_status.text().startswith('0.0')
            win.toggle_acquisition();phase=3
        elif phase==3 and win.status.currentMessage()=='已连接 · 已停止':
            assert not win.sampling_indicator.active
            assert not win.sampling_indicator.timer.isActive()
            assert win.sampling_indicator.isHidden()
            # A new single acquisition must not count the idle interval as a frame.
            win.start(False);phase=4
        elif phase==4 and win.status.currentMessage()=='已连接 · 采集完成':
            assert 'Hz' in win.measure_status.text()
            assert not win.sampling_indicator.active
            phase=5;timer.stop();win.close();app.quit()
    except BaseException as error:
        errors.append(error);timer.stop();win.close();app.quit()
timer=QtCore.QTimer();timer.timeout.connect(poll);timer.start(20)
app.exec()
if errors:raise errors[0]
assert phase==5 and animated
''',tmp_path)
