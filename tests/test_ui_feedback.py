import os
import subprocess
import sys


def test_auto_updates_display_and_dialog_follows_theme(tmp_path):
    script='''
from argparse import Namespace
from PySide6 import QtCore,QtGui,QtWidgets as W
from spectradesk.app import Window
app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'));win.show()
errors=[];phase=0
def poll():
    global phase
    try:
        if not win.ready:return
        if phase==0:
            assert win.connect_button.objectName()=='disconnect'
            win.integration.setValue(333)
            assert win.integration_label.text()=='积分时间 · 333'
            win.request_auto();phase=1;return
        if win.auto_busy:return
        assert win.integration.value()==48
        assert win.integration.text()=='48'
        assert win.integration_label.text()=='积分时间 · 48'
        assert win.integration.isEnabled()
        store=QtCore.QSettings('SpectraDesk','SpectraDesk')
        assert store.value('integration',type=int)==48
        for index,base,text in ((2,'#18212c','#dce4ed'),(1,'#ffffff','#263349')):
            win.theme.setCurrentIndex(index)
            dialog=win.create_save_dialog();dialog.show();app.processEvents()
            assert dialog.testOption(W.QFileDialog.Option.DontUseNativeDialog)
            edit=dialog.findChild(W.QLineEdit,'fileNameEdit')
            assert edit is not None
            assert edit.palette().color(QtGui.QPalette.ColorRole.Base).name()==base
            assert edit.palette().color(QtGui.QPalette.ColorRole.Text).name()==text
            assert edit.palette().color(QtGui.QPalette.ColorRole.HighlightedText).name()=='#ffffff'
            tree=dialog.findChild(W.QTreeView,'treeView')
            assert tree is not None
            assert tree.palette().color(QtGui.QPalette.ColorRole.Text).name()==text
            dialog.reject();dialog.deleteLater()
        win.set_controls(False)
        assert win.connect_button.objectName()=='connect'
        assert win.connect_button.text()=='连接光谱仪'
        timer.stop();win.close();app.quit()
    except BaseException as error:
        errors.append(error);timer.stop();win.close();app.quit()
timer=QtCore.QTimer();timer.timeout.connect(poll);timer.start(40)
app.exec()
if errors:raise errors[0]
assert phase==1
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_inline_notices_do_not_move_or_resize_main_plot(tmp_path):
    script='''
from argparse import Namespace
import numpy as np
from PySide6 import QtWidgets as W
from spectradesk.app import Window
app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'))
win._startup_timer.stop();win.show()
def settle():
    for _ in range(3):app.processEvents()
try:
    x=np.linspace(279,975,2048)
    base=dict(wave=x,mean=np.full(2048,5000.),extra=np.zeros(2048),parameter=3000,
        average=2,demo=True,device=dict(serial='test'),index=1,elapsed=.04)
    for theme in (1,2):
        win.theme.setCurrentIndex(theme)
        win.frame_data=dict(base,adc_frames=np.full((2,2048),32760,dtype=np.uint16))
        win.render();settle()
        rect=win.plot.geometry();size=win.size()
        for clipped in (True,False,True,False):
            win.frame_data=dict(base,adc_frames=np.full((2,2048),10000 if clipped else 32760,dtype=np.uint16))
            win.render();settle()
            assert win.plot.geometry()==rect and win.size()==size
            assert bool(win.warning_label.text())==clipped
            if clipped:
                assert win.warning_label.text().startswith('❗ ')
                assert '削顶' in win.warning_label.text()
                assert win.warning_label.geometry().left()>win.navigation_label.geometry().left()
            assert win.warning_label.geometry().center().y()==win.navigation_label.geometry().center().y()
        message='设备通讯错误'+chr(10)+('很长的提示文字 '*60)
        win.on_error(message);settle()
        assert win.plot.geometry()==rect and win.size()==size
        assert not win.warning_label.wordWrap()
        assert chr(10) not in win.warning_label.text()
        assert win.warning_label.toolTip()==' '.join(message.split())
        win.show_notice('曝光 20 ms · 摄像头灰度 DN',warning=False);settle()
        assert not win.warning_label.text().startswith('❗')
        assert win.plot.geometry()==rect
finally:
    win.close();app.processEvents()
'''
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=20,
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1'))
    assert result.returncode==0,result.stdout+result.stderr
