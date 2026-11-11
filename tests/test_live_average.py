import os
import subprocess
import sys


def test_continuous_average_change_keeps_groups_complete(tmp_path):
    script='''
import time
from argparse import Namespace
import numpy as np
from PySide6 import QtCore,QtWidgets as W
from spectradesk import worker as module
from spectradesk.app import Window
class FakeDevice:
    parameter=250
    @classmethod
    def device_available(cls):return True
    def open(self):return dict(model='FLA5000',serial='test',firmware='VER7.1',anchors=[]),np.linspace(300,900,2048),np.zeros(2048)
    def set_parameter(self,p):self.parameter=p
    def check_connected(self):pass
    def capture(self,average):
        time.sleep(.15)
        return np.full((average,2048),30000,dtype=np.uint16)
    def close(self):pass
module.Driver=FakeDevice
app=W.QApplication([]);win=Window(Namespace(demo=False,connect=False,smoke=None,renderer='raster'));win.show()
phase=0;old_seen=False;errors=[]
def poll():
    global phase,old_seen
    try:
        if phase==0 and win.ready:
            win.average.setValue(2);win.start(True);phase=1
        elif phase==1 and win.sampling_indicator.active:
            assert win.average.isEnabled()
            win.average.setValue(4);phase=2
        elif phase==2 and win.frame_data is not None:
            f=win.frame_data
            assert f['adc_frames'].shape[0]==f['average']
            if f['average']==2:old_seen=True
            if f['average']==4:
                assert old_seen and win.worker.running
                phase=3;timer.stop();win.close();app.quit()
    except BaseException as error:
        errors.append(error);timer.stop();win.close();app.quit()
timer=QtCore.QTimer();timer.timeout.connect(poll);timer.start(15)
app.exec()
if errors:raise errors[0]
assert phase==3
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
