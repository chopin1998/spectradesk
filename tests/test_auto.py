import time
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer
from spectradesk.driver import Driver
from spectradesk.worker import Acquisition

@pytest.fixture(scope='module')
def app():
    return QCoreApplication.instance() or QCoreApplication([])

class FakeDriver:
    auto_steps=Driver.auto_steps
    def __init__(self,signal=100,parameter=250):
        self.parameter=parameter;self.signal=signal;self.captures=0;self.closed=False
    def set_parameter(self,p):self.parameter=p
    def capture(self,average):
        self.captures+=1
        counts=np.full((average,2048),1900.)
        counts[:,500]=min(16640,1900+self.signal*self.parameter)
        return (32767-counts).astype(np.uint16)
    def close(self):self.closed=True


def run_auto(app,driver,hook=None,average=1):
    worker=Acquisition();worker.ready=True;worker.driver=driver;worker.average=average
    worker.timer=QTimer(worker);worker.running=True
    messages=[];states=[];errors=[]
    worker.auto_done.connect(lambda p,m:messages.append((p,m)))
    worker.error.connect(errors.append)
    loop=QEventLoop();worker.auto_done.connect(loop.quit)
    def state(text):
        states.append(text)
        if hook:hook(worker,text)
    worker.state.connect(state)
    timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(loop.quit);timeout.start(2000)
    worker.auto();loop.exec();timeout.stop()
    worker.timer.stop()
    if worker.auto_timer:worker.auto_timer.stop()
    assert messages,states
    assert not errors
    assert worker.ready and not driver.closed
    assert worker.auto_iterator is None
    return worker,messages,states


def test_converges_with_yields_between_frames(app):
    driver=FakeDriver()
    worker,messages,states=run_auto(app,driver)
    assert abs(messages[0][0]-101)<=1
    assert '自动完成' in messages[0][1]
    assert any('1/3 帧' in s for s in states)
    assert worker.running

@pytest.mark.parametrize('signal,expected,reason',[(0,30000,'光线过弱'),(2000,15,'光线过强')])
def test_unreachable_target_keeps_device_connected(app,signal,expected,reason):
    worker,messages,_=run_auto(app,FakeDriver(signal))
    assert messages[0][0]==expected
    assert reason in messages[0][1]
    assert worker.running


def test_cancel_is_processed_between_usb_frames(app):
    driver=FakeDriver()
    def cancel(worker,text):
        if '1/3 帧' in text:QTimer.singleShot(0,worker.stop)
    worker,messages,_=run_auto(app,driver,cancel)
    assert '已取消' in messages[0][1]
    assert driver.captures==1
    assert not worker.running


def test_timeout_keeps_last_hardware_parameter(app):
    driver=FakeDriver()
    def expire(worker,text):
        if '1/3 帧' in text:worker.auto_started=time.monotonic()-31
    worker,messages,_=run_auto(app,driver,expire)
    assert '30 秒时限' in messages[0][1]
    assert messages[0][0]==driver.parameter
    assert driver.captures==1


def test_transport_failure_closes_device(app):
    worker=Acquisition();worker.ready=True;worker.driver=FakeDriver()
    driver=worker.driver
    def fail(average):raise RuntimeError('USB timeout')
    driver.capture=fail
    errors=[];worker.error.connect(errors.append)
    worker.auto();worker.auto_timer.stop();worker.auto_step()
    assert errors==['USB timeout']
    assert not worker.ready and driver.closed
    assert worker.auto_iterator is None


def test_auto_clamps_high_manual_parameter_before_first_capture():
    driver=FakeDriver(parameter=65535)
    steps=driver.auto_steps()
    assert next(steps)==(1,1,30000)
    assert driver.parameter==30000
    steps.close()


@pytest.mark.parametrize('seconds,current,expected',[
    (1.1,8,1),(.2,8,1),(.1,4,4),(.05,1,1),(.015,1,4),(.005,2,8),(.01,8,8),(.125,8,8)
])
def test_auto_average_rate_policy(seconds,current,expected):
    from spectradesk.worker import choose_auto_average
    assert choose_auto_average(seconds,current)==expected


@pytest.mark.parametrize('seconds,current,expected',[(.2,8,1),(.015,1,4),(.005,2,8)])
def test_auto_uses_final_frame_timing_and_updates_average(app,monkeypatch,seconds,current,expected):
    clock=[100.]
    monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    driver=FakeDriver()
    original=driver.capture
    def capture(n):
        # Early search rounds are deliberately slower, and must be ignored.
        clock[0]+=seconds if abs(driver.parameter-101)<=1 else .7
        return original(n)
    driver.capture=capture
    worker,messages,_=run_auto(app,driver,average=current)
    assert worker.average==expected
    assert f'平均 {expected} 帧' in messages[0][1]


def test_cancel_preserves_average(app):
    def cancel(worker,text):
        if '1/3 帧' in text:QTimer.singleShot(0,worker.stop)
    worker,_,_=run_auto(app,FakeDriver(),cancel,average=6)
    assert worker.average==6


def test_worker_average_limit():
    worker=Acquisition()
    worker.set_average(64);assert worker.average==8
    worker.set_average(0);assert worker.average==1
