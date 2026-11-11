"""Run on a real desktop GL context; no spectrometer or user settings are used."""
import os,tempfile
config=tempfile.TemporaryDirectory(prefix='spectradesk-gpu-check-');os.environ['XDG_CONFIG_HOME']=config.name
from argparse import Namespace
from types import SimpleNamespace
import numpy as np
from PySide6 import QtCore,QtGui,QtOpenGL,QtTest,QtWidgets as W
from spectradesk import gpu_curve
from spectradesk.app import Window

app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None))
win.show();QtTest.QTest.qWait(200)
x=np.linspace(279,975,2048);y=np.full(2048,5000.)
frame=dict(wave=x,mean=y,extra=np.zeros(2048),adc_frames=np.full((2,2048),30000,dtype=np.uint16),parameter=3000,average=2,demo=True,device=dict(serial='test'),index=1,elapsed=.04)
clock=[0.];gpu_curve.time=SimpleNamespace(monotonic=lambda:clock[0])

def capture():
    vp=win.plot.viewport();vp.makeCurrent();gl=vp.getFunctions()
    size=QtCore.QSize(round(vp.width()*vp.devicePixelRatioF()),round(vp.height()*vp.devicePixelRatioF()))
    fbo=QtOpenGL.QOpenGLFramebufferObject(size)
    assert fbo.isValid()
    try:
        fbo.bind();gl.glViewport(0,0,size.width(),size.height());gl.glDisable(0x0C11);gl.glDisable(0x0BE2)
        gl.glClearColor(0,0,0,0);gl.glClear(0x4000)
        win.curve.glstate.output_fbo=fbo.handle();win.curve.paintGL(vp);gl.glFinish()
        image=fbo.toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
        return np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.width(),4).copy()
    finally:
        gl.glBindFramebuffer(0x8D40,vp.context().defaultFramebufferObject());fbo=None;vp.doneCurrent()

try:
    images=[];win.frame_data=frame
    for mode in range(4):
        win.mode.setCurrentIndex(mode);win.render();QtTest.QTest.qWait(50)
        assert not win.curve.last_error,win.curve.last_error
        pixels=capture();images.append(pixels)
        assert np.count_nonzero(pixels[:,:,3])>100
        assert np.array_equal(win.curve.getData()[1],win.displayed)
    win.plot.viewport().repaint()
    visible=win.curve.capture_viewport(win.plot.viewport())
    assert not visible.isNull()
    colored=images[1][images[1][:,:,3]>100][:,:3]
    assert len(np.unique(colored,axis=0))>32,'Rainbow shader produced a single color'
    stops=np.array([0,.15,.25,.375,.5,.625,.8,1.])
    colors=np.array([[144,104,233],[101,136,255],[72,213,236],[120,229,157],[229,228,114],[243,170,103],[237,110,117],[174,85,107]])
    for wave in (400.,546.,650.,750.):
        point=win.spectrum_view.mapViewToScene(QtCore.QPointF(wave,5000.))
        column=round(point.x()*win.plot.viewport().devicePixelRatioF())
        actual=images[1][:,column,:][images[1][:,column,3]>100][0,:3]
        expected=np.array([np.interp((wave-380)/400,stops,colors[:,i]) for i in range(3)])
        assert np.max(abs(actual.astype(float)-expected))<5,(wave,actual,expected)
    assert np.count_nonzero(images[2][:,:,3])>10*np.count_nonzero(images[1][:,:,3]),'Fill is missing'
    # A new line lower on the same axes must leave a fading, correctly located old trace.
    old=images[3];old_mask=old[:,:,3]>200
    clock[0]=.55;win.frame_data=dict(frame,mean=np.full(2048,1000.));win.render()
    faded=capture()
    assert old_mask.any() and faded[:,:,3][old_mask].mean()<old[:,:,3][old_mask].mean()*.5
    assert faded[:,:,3][old_mask].mean()>old[:,:,3][old_mask].mean()*.2
    assert np.any((faded[:,:,3]>200)&~old_mask),'New spectrum did not upload to GPU'
    # Repeated repaint must not accumulate brightness or alter temporal history.
    assert np.array_equal(faded,capture())
    win.plot.setXRange(400,700,padding=0)
    cleared=capture()
    assert cleared[:,:,3][old_mask].max()==0,'Old history survived coordinate change'
    assert np.array_equal(y,frame['mean'])
    print('PASS: GPU rainbow colors, fill, data upload, exponential persistence, repaint invariance, range reset and cleanup')
finally:win.close()
