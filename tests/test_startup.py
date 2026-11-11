import os
from pathlib import Path
import subprocess
import sys


def test_startup_connects_without_capturing_and_theme_is_visible(tmp_path):
    script='''
from argparse import Namespace
from PySide6 import QtCore,QtWidgets
from spectradesk import app as module
from spectradesk.worker import Acquisition
# Exercise default startup with a simulated device behind the real worker.
module.Acquisition=lambda demo: Acquisition(True)
app=QtWidgets.QApplication([])
win=module.Window(Namespace(demo=False,connect=False,smoke=None,renderer='raster'));win.show()
errors=[]
def verify():
    try:
        assert win.ready
        assert win.frame_data is None
        assert win.worker.counter==0
        assert not win.worker.running
        assert not win.worker.timer.isActive()
        assert win.worker.parameter==win.integration.value()
        button=win.theme
        assert button.isVisible()
        assert win.rect().contains(button.mapTo(win,button.rect().center()))
        for index,name in ((1,'浅色'),(2,'暗色'),(0,'跟随系统')):
            button.click()
            assert win.theme.currentIndex()==index
            assert win.theme.currentText()==name
            assert button.text()=='主题：'+name
        win.theme.setCurrentIndex(2)
        assert win.plot.backgroundBrush().color().name()=='#18212c'
        win.theme.setCurrentIndex(1)
        assert win.plot.backgroundBrush().color().name()=='#ffffff'
        win.theme.setCurrentIndex(0)
    except BaseException as error:errors.append(error)
    finally:win.close();app.quit()
QtCore.QTimer.singleShot(800,verify)
app.exec()
if errors:raise errors[0]
assert QtCore.QSettings('SpectraDesk','SpectraDesk').value('theme',type=int)==0
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_only_one_process_can_hold_instance_lock_and_crash_recovers(tmp_path):
    from spectradesk.app import acquire_instance_lock
    holder='''
import sys
from spectradesk.app import acquire_instance_lock
lock=acquire_instance_lock(sys.argv[1])
assert lock is not None
print('locked',flush=True)
sys.stdin.read()
'''
    proc=subprocess.Popen([sys.executable,'-c',holder,str(tmp_path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert proc.stdout.readline().strip()=='locked'
        assert acquire_instance_lock(str(tmp_path)) is None
        proc.kill();proc.wait(timeout=5)
        lock=acquire_instance_lock(str(tmp_path))
        assert lock is not None
        lock.unlock()
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=5)
        proc.stdin.close();proc.stdout.close()
