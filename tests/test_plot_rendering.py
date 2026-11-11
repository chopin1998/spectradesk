import os
import subprocess
import sys


def test_dark_axis_floor_does_not_change_data_or_hide_weak_peaks(tmp_path):
    script='''
from argparse import Namespace
import numpy as np
from PySide6 import QtCore,QtWidgets as W
from spectradesk.app import Window
from spectradesk.analysis import analyze,display_smooth
app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None));win.show()
errors=[]
def verify():
    try:
        x=np.linspace(279,975,2048);rng=np.random.default_rng(123)
        weak=rng.normal(0,1,2048)+80*np.exp(-.5*((x-546)/2)**2)
        assert analyze(x,weak,350,900)
        for parameter,y in enumerate((rng.normal(0,12,2048),weak,weak*150),start=100):
            before=y.copy()
            win.frame_data=dict(wave=x,mean=y,extra=np.zeros(2048),adc_frames=np.full((2,2048),32760,dtype=np.uint16),parameter=parameter,average=2,demo=True,device=dict(serial='test'),index=1,elapsed=.1)
            win.smooth.setValue(1)
            for mode in range(4):
                win.mode.setCurrentIndex(mode);win.render();app.processEvents()
                assert np.array_equal(y,before)
                assert np.allclose(win.curve.getData()[1],display_smooth(y,1))
                lo,hi=win.spectrum_view.viewRange()[1]
                assert hi-lo>=200
                assert lo<=float(win.displayed.min()) and hi>=float(win.displayed.max())
                if parameter>=101:assert win.peaks
            if parameter==102:assert hi>9000
    except BaseException as error:errors.append(error)
    finally:win.close();app.quit()
QtCore.QTimer.singleShot(400,verify)
app.exec()
if errors:raise errors[0]
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
