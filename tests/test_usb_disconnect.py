import os
from pathlib import Path
import shlex
import subprocess
import sys

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer
from spectradesk.driver import Driver,DeviceDisconnectedError
from spectradesk import worker as module


def test_native_presence_checks_original_device_without_usb_commands(tmp_path):
    root=Path(__file__).parents[1]
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libusb-1.0'],text=True))
    executable=tmp_path/'presence'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(root/'tests/native/test_presence.c'),'-o',str(executable),*flags],check=True)
    subprocess.run([str(executable)],check=True,timeout=5)


def test_libusb_no_device_is_reported_as_disconnected():
    driver=object.__new__(Driver)
    with pytest.raises(DeviceDisconnectedError,match='USB 设备已断开'):
        driver.check(-4)


class FakeDevice:
    def __init__(self):self.present=True;self.closed=False;self.checks=0
    def open(self):return dict(model='FLA5000',serial='test',firmware='VER7.1',anchors=[]),np.arange(2048),np.zeros(2048)
    def check_connected(self):
        self.checks+=1
        if not self.present:raise DeviceDisconnectedError('USB 设备已断开')
    def close(self):self.closed=True


def test_idle_unplug_stops_monitor_and_allows_fresh_connection(monkeypatch):
    app=QCoreApplication.instance() or QCoreApplication([])
    devices=[]
    def create():
        device=FakeDevice();devices.append(device);return device
    create.device_available=lambda: not devices or devices[-1].present
    monkeypatch.setattr(module,'Driver',create)
    worker=module.Acquisition();states=[];connections=[]
    worker.state.connect(states.append);worker.connection_changed.connect(connections.append)
    worker.connect_device()
    assert worker.ready and worker.presence_timer.isActive()
    assert not worker.running and not worker.timer.isActive()
    devices[0].present=False
    loop=QEventLoop()
    def changed(ready):
        if not ready:loop.quit()
    worker.connection_changed.connect(changed)
    timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(loop.quit);timeout.start(2000)
    loop.exec();timeout.stop()
    assert not worker.ready and devices[0].closed
    assert worker.counter==0 and devices[0].checks>0
    assert worker.presence_timer is None and worker.timer is None
    assert connections==[True,False] and states[-1]=='USB 已断开'
    devices[0].present=True
    worker.connect_device()
    assert worker.ready and len(devices)==2 and worker.presence_timer.isActive()
    worker.disconnect_device()
    assert not worker.ready and devices[1].closed
    assert worker.presence_timer is None and connections==[True,False,True,False]
    worker.discovery_timer.stop()


def test_device_panel_disables_missing_device_and_supports_replug(tmp_path):
    script='''
from argparse import Namespace
import numpy as np
from PySide6 import QtCore,QtWidgets as W
from spectradesk import worker as module
from spectradesk.driver import DeviceDisconnectedError
from spectradesk.app import Window
class FakeDevice:
    parameter=None;plugged=False
    @classmethod
    def device_available(cls):return cls.plugged
    def __init__(self):self.present=True;self.captures=0
    def open(self):return dict(model='FLA5000',serial='test',firmware='VER7.1',anchors=[]),np.arange(2048),np.zeros(2048)
    def set_parameter(self,value):self.parameter=value
    def check_connected(self):
        if not self.present:raise DeviceDisconnectedError('USB 设备已断开')
    def close(self):pass
module.Driver=FakeDevice
app=W.QApplication([])
win=Window(Namespace(demo=False,connect=False,smoke=None));win.show()
phase=0;errors=[]
def poll():
    global phase
    try:
        assert not hasattr(win,'badge')
        if phase==0 and win.device_status.text()=='未找到光谱仪':
            assert not win.ready and not win.connect_button.isEnabled()
            assert win.worker.driver is None
            assert win.device_status.parent() is win.connect_button.parent()
            FakeDevice.plugged=True;phase=1
        elif phase==1 and win.connect_button.isEnabled():
            assert win.device_present and not win.ready
            win.toggle_connection();phase=2
        elif phase==2 and win.ready:
            assert win.device_status.text()=='USB 已连接'
            assert win.worker.counter==0
            win.worker.driver.present=False;FakeDevice.plugged=False;phase=3
        elif phase==3 and win.device_status.text()=='USB 已断开':
            assert not win.ready
            assert win.connect_button.text()=='连接光谱仪'
            assert win.connect_button.objectName()=='connect'
            assert not win.connect_button.isEnabled()
            assert not win.run.isEnabled() and not win.single.isEnabled()
            assert not win.auto_button.isEnabled() and not win.info_button.isEnabled()
            assert win.serial_label.text()=='设备未连接'
            FakeDevice.plugged=True;phase=4
        elif phase==4 and win.connect_button.isEnabled():
            win.toggle_connection();phase=5
        elif phase==5 and win.ready:
            assert win.device_status.text()=='USB 已连接'
            win.toggle_connection();phase=6
        elif phase==6 and win.status.currentMessage()=='未连接':
            assert win.device_status.text()=='已找到设备 · 未连接'
            assert not win.ready and win.connect_button.isEnabled()
            assert win.connect_button.objectName()=='connect'
            phase=7;timer.stop();win.close();app.quit()
    except BaseException as error:
        errors.append(error);timer.stop();win.close();app.quit()
timer=QtCore.QTimer();timer.timeout.connect(poll);timer.start(50)
app.exec()
if errors:raise errors[0]
assert phase==7
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('mode',['continuous','single','auto'])
def test_usb_error_during_capture_immediately_disconnects(monkeypatch,mode):
    app=QCoreApplication.instance() or QCoreApplication([])
    class FailingCapture(FakeDevice):
        parameter=250
        def set_parameter(self,parameter):self.parameter=parameter
        def capture(self,average):raise DeviceDisconnectedError('USB 设备已断开')
        def auto_steps(self):
            self.capture(1)
            yield 1,1,250
    device=FailingCapture()
    def create():return device
    create.device_available=lambda:True
    monkeypatch.setattr(module,'Driver',create)
    worker=module.Acquisition();states=[];connections=[]
    worker.state.connect(states.append);worker.connection_changed.connect(connections.append)
    worker.connect_device()
    if mode=='auto':
        worker.auto();worker.auto_timer.stop();worker.check_connection()
        assert device.checks==0
        worker.auto_step()
    else:
        worker.running=True;worker.check_connection()
        assert device.checks==0
        worker.start(250,1,mode=='continuous')
    assert not worker.ready and device.closed
    assert worker.presence_timer is None and worker.timer is None
    assert worker.auto_iterator is None
    assert states[-1]=='USB 已断开' and connections==[True,False]
    worker.discovery_timer.stop()
