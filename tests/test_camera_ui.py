import os,sys,subprocess

def test_camera_ui(tmp_path):
    code='''
import numpy as np
from argparse import Namespace
from PySide6 import QtWidgets as W,QtCore
from spectradesk.app import Window
from spectradesk.camera import CameraProfile
from spectradesk.camera_dialog import CameraDialog
app=W.QApplication([]);win=Window(Namespace(demo=True,smoke=None,renderer='raster'))
errors=[]
def check():
 try:
  p=CameraProfile();x,e=p.wavelengths();y=50*np.exp(-((x-546)/2)**2)
  f=dict(wave=x,extra=e,mean=y,adc_frames=y[None,:],backend='camera',camera_image=np.zeros((1080,1920,3),np.uint8),parameter=0,saturated=False,elapsed=.1,index=1,device={},utc='test')
  win.frame_data=f;win.raw_preview_toggle.setChecked(True);app.processEvents();assert win.raw_band.image is not None;assert win.raw_band.bounds.width()>0;np.testing.assert_array_equal(win.pixel_curve.yData,f['mean']);win.render();app.processEvents();win.align_raw_band();app.processEvents();win.align_raw_band();app.processEvents();a=win.plot.viewport().mapToGlobal(win.plot.mapFromScene(win.spectrum_view.mapViewToScene(QtCore.QPointF(546,0))));b=win.raw_band_plot.mapToGlobal(QtCore.QPoint(win.raw_band_plot.screen_x(546),0));assert abs(a.x()-b.x())<=2,(a,b);baseline=(win.plot.geometry(),win.raw_preview.geometry(),win.spectrum_view.viewRange());\n  for _ in range(30):\n   win.update_raw_preview();win.align_raw_band();app.processEvents();assert (win.plot.geometry(),win.raw_preview.geometry(),win.spectrum_view.viewRange())==baseline\n  win.raw_preview_toggle.setChecked(False);win.render();assert win.peaks and win.metric_units[2].text()=='DN'
  assert 45 < win.spectrum_view.viewRange()[1][1] < 65
  assert not win.plot.getAxis('bottom').autoSIPrefix
  win.frame_data=dict(f,backend='fla5000');win.render();assert win.spectrum_view.viewRange()[1][1] >= 200
  win.frame_data=f;win.render();assert win.spectrum_view.viewRange()[1][1] < 65
  d=CameraDialog(p,'/dev/video0',f,win,reference_frame=dict(wave=x,corrected=y,utc='test'));assert d.calibration_mode.currentIndex()==1;assert d.reference_curve.yData is not None;d.show();app.processEvents();assert not d.preview.pixmap().isNull();d.close()
  win.capture_camera_dark();assert np.max(np.abs(win.corrected))==0
  win.capture_camera_dark();assert np.max(win.corrected)>40
 except BaseException as ex:errors.append(ex)
 finally:win.close();app.quit()
QtCore.QTimer.singleShot(400,check);app.exec()
if errors:raise errors[0]
'''
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path)),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
