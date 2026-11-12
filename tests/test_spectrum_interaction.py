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
