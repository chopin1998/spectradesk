import sys,time,json,tempfile,os
settings_dir=tempfile.TemporaryDirectory(prefix="spectradesk-benchmark-")
os.environ["XDG_CONFIG_HOME"]=settings_dir.name
from pathlib import Path
from argparse import Namespace
import numpy as np
from PySide6 import QtCore,QtGui,QtTest,QtWidgets as W
from spectradesk.app import Window
backend=sys.argv[1]
fmt=QtGui.QSurfaceFormat();fmt.setSwapInterval(0);QtGui.QSurfaceFormat.setDefaultFormat(fmt)
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,QtCore.QSettings.Scope.UserScope,settings_dir.name)
app=W.QApplication([])
assert Path(QtCore.QSettings('SpectraDesk','SpectraDesk').fileName()).is_relative_to(settings_dir.name)
win=Window(Namespace(demo=True,connect=False,smoke=None,renderer=backend));win.resize(1180,760);win.show();win.smooth.setValue(1);win.overlay.setChecked(True);win.theme.setCurrentIndex(1);app.processEvents()
rng=np.random.default_rng(123);x=np.linspace(279,975,2048);noise=rng.normal(0,12,2048)
frame=dict(wave=x,extra=np.zeros(2048),adc_frames=np.full((2,2048),32760,dtype=np.uint16),parameter=3000,average=2,demo=True,device=dict(serial='test'),index=1,elapsed=.04)
try:
 results=[]
 for mode in range(4):
  win.mode.setCurrentIndex(mode)
  for signal in ['peak','noise']:
   y=noise.copy()
   if signal=='peak':y+=10000*np.exp(-.5*((x-546)/2)**2)
   win.frame_data=dict(frame,mean=y);win.axis_context=None
   def draw():
    win.render();win.plot.viewport().repaint();app.processEvents()
    if backend=='opengl':
     vp=win.plot.viewport();vp.makeCurrent()
     assert vp.context() and vp.context().isValid(),'No valid OpenGL context'
     vp.context().functions().glFinish();vp.doneCurrent()
   for _ in range(12):draw();QtTest.QTest.qWait(10)
   if backend=='opengl':
    assert win.curve.curve.glstate is not None,'Curve did not use GPU rendering'
    assert not win.curve.last_error,win.curve.last_error
   wall=time.perf_counter();cpu=time.process_time()
   for i in range(50):
    win.frame_data=dict(frame,mean=y+np.sin(i)*.2);draw()
   results.append(dict(backend=backend,mode=mode,signal=signal,cpu_ms=(time.process_time()-cpu)*20,wall_ms=(time.perf_counter()-wall)*20))
   if signal=='peak' and len(sys.argv)>2:
    screenshot=Path(sys.argv[2]);screenshot=screenshot.with_name(screenshot.stem+f'-{mode}'+screenshot.suffix)
    QtTest.QTest.qWait(50)
    win.plot.viewport().repaint()
    win.curve.capture_viewport(win.plot.viewport()).save(str(screenshot)) if backend=='opengl' else win.plot.viewport().grab().save(str(screenshot))
finally:
 win.close()
print(json.dumps(results),flush=True)
