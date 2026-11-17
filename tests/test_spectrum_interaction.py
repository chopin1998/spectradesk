import os,sys,subprocess

def test_shared_navigation_and_dual_axis_annotations(tmp_path):
    code='''
from PySide6 import QtCore,QtWidgets as W
import numpy as np
from types import SimpleNamespace
from spectradesk.spectrum_plot import SpectrumPlot
from spectradesk.plot_view import SpectrumViewBox
app=W.QApplication([]);plot=SpectrumPlot(renderer='raster');plot.resize(800,500);plot.show();app.processEvents()
try:
 plot.set_display_range(400,700);view=plot.getViewBox()
 class Event:
  def scenePos(self):return view.mapViewToScene(QtCore.QPointF(550,0))
  def delta(self):return 120
  def accept(self):pass
 view.wheelEvent(Event());zoom=tuple(view.viewRange()[0]);assert abs(zoom[1]-zoom[0]-282)<1e-5
 for _ in range(20):plot.set_display_range(400,700)
 np.testing.assert_allclose(view.viewRange()[0],zoom)
 for _ in range(200):view.wheelEvent(Event())
 assert abs(view.viewRange()[0][1]-view.viewRange()[0][0]-5)<1e-5
 class Out(Event):
  def delta(self):return -12000
 for _ in range(200):view.wheelEvent(Out())
 np.testing.assert_allclose(view.viewRange()[0],[400,700])
 view.mouseDoubleClickEvent(Event());np.testing.assert_allclose(view.viewRange()[0],[400,700])
 right=SpectrumViewBox();plot.scene().addItem(right);right.setXLink(view);right.navigation_target=view
 x=np.array([400.,500.,600.]);peak=SimpleNamespace(wavelength=500.)
 plot.set_spectrum_series([dict(name='FLA5000',x=x,y=np.array([100.,200.,300.]),peaks=[peak],unit='counts'),dict(name='摄像头',x=x,y=np.array([10.,20.,30.]),peaks=[peak],unit='DN',view=right)])
 plot._cursor_wave=500.;plot.update_spectrum_cursor()
 assert '200.00 counts' in plot.readout.toPlainText() and '20.00 DN' in plot.readout.toPlainText()
 for name,y in [('FLA5000',200.),('摄像头',20.)]:
  series=plot._series[name]
  assert series['cursor'].getData()[1][0]==y and series['peaks'].getData()[1][0]==y
  assert series['labels'][0].toPlainText()=='500.0'
 assert plot._series['摄像头']['cursor'].getViewBox() is right
 plot.set_spectrum_series([]);assert not plot._series['摄像头']['cursor'].isVisible()
finally:plot.close()
'''
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path)),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_locked_y_axis_wheel_scales_and_survives_frames(tmp_path):
    code='''
from argparse import Namespace
from PySide6 import QtCore,QtGui,QtWidgets as W
import numpy as np
from spectradesk.app import Window
app=W.QApplication([]);win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'))
win._startup_timer.stop();win.show();app.processEvents()
try:
 x=np.linspace(279,975,2048)
 win.frame_data=dict(wave=x,mean=np.full(2048,100.),extra=np.zeros(2048),adc_frames=np.full((2,2048),32760,dtype=np.uint16),parameter=3000,average=2,demo=True,device=dict(serial='test'),index=1,elapsed=.04)
 win.render();app.processEvents()
 plot=win.plot;view=win.spectrum_view;axis=plot.getAxis('left');viewport=plot.viewport()
 def wheel(item,delta):
  scene=item.sceneBoundingRect().center()
  if item is axis:scene.setX((axis.sceneBoundingRect().left()+view.sceneBoundingRect().left())/2)
  pos=plot.mapFromScene(scene)
  event=QtGui.QWheelEvent(QtCore.QPointF(pos),QtCore.QPointF(viewport.mapToGlobal(pos)),QtCore.QPoint(),QtCore.QPoint(0,delta),QtCore.Qt.MouseButton.NoButton,QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.NoScrollPhase,False)
  W.QApplication.sendEvent(viewport,event);app.processEvents()
 before_x=tuple(view.viewRange()[0]);before_y=tuple(view.viewRange()[1])
 wheel(axis,120)
 np.testing.assert_allclose(view.viewRange()[0],before_x);np.testing.assert_allclose(view.viewRange()[1],before_y)
 zero_fraction=lambda limits: -limits[0]/(limits[1]-limits[0])
 win.lock_y_axis.setChecked(True);wheel(axis,120)
 zoom=tuple(view.viewRange()[1]);assert zoom[1]-zoom[0] < before_y[1]-before_y[0]
 np.testing.assert_allclose(view.viewRange()[0],before_x)
 np.testing.assert_allclose(zero_fraction(zoom),zero_fraction(before_y),atol=1e-12)
 win.frame_data=dict(win.frame_data,mean=np.full(2048,10000.));win.render()
 np.testing.assert_allclose(view.viewRange()[1],zoom)
 wheel(axis,-120);assert view.viewRange()[1][1]-view.viewRange()[1][0] > zoom[1]-zoom[0]
 np.testing.assert_allclose(zero_fraction(view.viewRange()[1]),zero_fraction(before_y),atol=1e-12)
 wheel(view,120);assert view.viewRange()[0][1]-view.viewRange()[0][0] < before_x[1]-before_x[0]
 win.lock_y_axis.setChecked(False);assert view.viewRange()[1][1]>10000
finally:win.close();app.processEvents()
'''
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_locked_y_wheel_stops_at_practical_limits(tmp_path):
    code="""
from argparse import Namespace
from PySide6 import QtWidgets as W
import numpy as np
from spectradesk.app import Window
app=W.QApplication([]);win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'))
win._startup_timer.stop()
try:
 x=np.linspace(279,975,2048)
 class Wheel:
  def __init__(self,delta):self.value=delta
  def delta(self):return self.value
  def accept(self):pass
 for backend,limits in [('fla5000',(100.,250.)),('camera',(1.,1024.))]:
  win.lock_y_axis.setChecked(False)
  win.frame_data=dict(wave=x,mean=np.full(2048,100.),extra=np.zeros(2048),adc_frames=np.full((2,2048),32760,dtype=np.uint16),parameter=3000,average=2,demo=True,device=dict(serial='test'),index=1,elapsed=.04,backend=backend)
  win.render();win.lock_y_axis.setChecked(True);view=win.spectrum_view
  zero=lambda: -view.viewRange()[1][0]/(view.viewRange()[1][1]-view.viewRange()[1][0])
  original=zero()
  for _ in range(250):view.wheelEvent(Wheel(240),axis=1)
  np.testing.assert_allclose(np.ptp(view.viewRange()[1]),limits[0],rtol=1e-8)
  np.testing.assert_allclose(zero(),original,atol=1e-8)
  for _ in range(250):view.wheelEvent(Wheel(-240),axis=1)
  np.testing.assert_allclose(np.ptp(view.viewRange()[1]),limits[1],rtol=1e-8)
  np.testing.assert_allclose(zero(),original,atol=1e-8)
  if backend=='fla5000':
   win.frame_data=dict(win.frame_data,mean=np.full(2048,400.));win.render()
   assert view.y_scale_limits==(100.,1000.)
   for _ in range(50):view.wheelEvent(Wheel(-240),axis=1)
   np.testing.assert_allclose(np.ptp(view.viewRange()[1]),1000.,rtol=1e-8)
   win.frame_data=dict(win.frame_data,mean=np.full(2048,10.));win.render()
   assert view.y_scale_limits==(100.,100.)
   before=np.ptp(view.viewRange()[1]);view.wheelEvent(Wheel(120),axis=1)
   assert 100.<np.ptp(view.viewRange()[1])<before
finally:win.close();app.processEvents()
"""
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
