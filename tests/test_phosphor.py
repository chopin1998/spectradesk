import os,subprocess,sys


def test_phosphor_decay_preserves_measurement_and_reset(tmp_path):
    script='''
from PySide6 import QtWidgets as W
from types import SimpleNamespace
import numpy as np
from spectradesk import phosphor as m
app=W.QApplication([]);clock=[0.];m.time=SimpleNamespace(monotonic=lambda:clock[0])
p=m.PhosphorImage();x=np.linspace(300,900,2048);y=100*np.exp(-.5*((x-500)/2)**2);before=y.copy();bounds=(300,900,0,150)
p.update_spectrum(x,y,bounds);old=p.history.copy()
clock[0]=.55;p.update_spectrum(x,y*0,bounds)
assert np.array_equal(y,before)
assert np.allclose(p.history[1:],old[1:]*np.exp(-1))
p.update_spectrum(x,y*0,(300,900,-50,200))
assert p.history.max()<=1 and np.count_nonzero(p.history)<1024
p.reset();assert p.history.max()==0 and not p.isVisible()
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
