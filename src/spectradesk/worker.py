from datetime import datetime, timezone
import time
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QThread
from .driver import Driver

class Acquisition(QObject):
    connected=Signal(object)
    frame=Signal(object)
    state=Signal(str)
    error=Signal(str)
    auto_done=Signal(int,str)
    integration_changed=Signal(int)
    def __init__(self,demo=False):
        super().__init__();self.demo=demo;self.driver=None;self.timer=None;self.running=False;self.ready=False
        self.parameter=25;self.average=1;self.counter=0;self.auto_timer=None;self.auto_iterator=None
    @Slot()
    def connect_device(self):
        try:
            if self.ready:return
            if self.demo:
                self.wave=np.linspace(279,975,2048,dtype=np.float32)
                self.extra=((self.wave<365)|(self.wave>872)).astype(np.uint8)
                self.meta=dict(model="FLA5000 · 模拟",serial="DEMO",firmware="模拟数据",anchors=[])
            else:
                self.driver=Driver();self.meta,self.wave,self.extra=self.driver.open()
            self.ready=True;self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.acquire)
            self.connected.emit(dict(meta=self.meta,wave=self.wave,extra=self.extra,demo=self.demo))
            self.state.emit("已连接 · 待采集")
        except Exception as e:self.fail(e)
    @Slot(int,int,bool)
    def start(self,parameter,average,continuous):
        if not self.ready or self.auto_iterator is not None:return
        try:
            self.parameter=parameter;self.average=average
            if self.driver:self.driver.set_parameter(parameter)
            self.integration_changed.emit(parameter)
            self.running=continuous
            if continuous:self.timer.start()
            self.state.emit("连续采集中" if continuous else "单次采集中")
            self.acquire()
        except Exception as e:self.fail(e)
    @Slot(int)
    def set_integration(self,parameter):
        if not self.ready or self.auto_iterator is not None:return
        try:
            if self.driver:self.driver.set_parameter(parameter)
            self.parameter=parameter;self.integration_changed.emit(parameter)
        except Exception as e:self.fail(e)
    @Slot()
    def acquire(self):
        if not self.ready or self.auto_iterator is not None:return
        started=time.monotonic()
        try:
            if QThread.currentThread().isInterruptionRequested():return
            if self.demo:
                x=self.wave;signal=np.zeros_like(x,dtype=np.float64)
                for center,width,height in [(405,1.4,650),(436,1.2,3200),(487,4.3,900),(546,1.8,7200),(580,15,1000),(611,1.5,10500),(631,2,650)]:
                    signal+=height*np.exp(-.5*((x-center)/width)**2)
                counts=1965+signal*self.parameter/50
                rng=np.random.default_rng()
                frames=np.clip(32767-np.minimum(counts,16640)+rng.normal(0,12,(self.average,2048)),0,65535).astype(np.uint16)
            else:frames=self.driver.capture(self.average)
            self.counter+=1
            self.frame.emit(dict(wave=self.wave,extra=self.extra,adc_frames=frames,mean=32767-frames.mean(axis=0),parameter=self.parameter,average=self.average,utc=datetime.now(timezone.utc).isoformat(),elapsed=time.monotonic()-started,index=self.counter,device=self.meta,demo=self.demo))
            if not self.running:self.state.emit("已连接 · 采集完成")
        except Exception as e:self.fail(e)
    @Slot()
    def stop(self):
        if self.auto_iterator is not None:
            self.finish_auto("自动积分已取消",resume=False)
        self.running=False
        if self.timer:self.timer.stop()
        self.state.emit("已连接 · 已停止" if self.ready else "未连接")
    @Slot()
    def auto(self):
        if not self.ready or self.auto_iterator is not None:return
        self.auto_resume=self.running;self.running=False
        if self.timer:self.timer.stop()
        self.auto_started=time.monotonic()
        self.auto_iterator=self.demo_auto_steps() if self.demo else self.driver.auto_steps()
        if self.auto_timer is None:
            self.auto_timer=QTimer(self);self.auto_timer.setSingleShot(True)
            self.auto_timer.timeout.connect(self.auto_step)
        self.state.emit("自动积分 · 正在寻找合适强度")
        self.auto_timer.start(0)

    def demo_auto_steps(self):
        yield 1,1,self.parameter
        self.parameter=48
        return 48,12000,1,0

    @Slot()
    def auto_step(self):
        if self.auto_iterator is None:return
        if QThread.currentThread().isInterruptionRequested():
            self.finish_auto("自动积分已取消",resume=False);return
        if time.monotonic()-self.auto_started>=30:
            self.finish_auto("自动积分已达 30 秒时限，请调整光强或手动设置");return
        try:
            step,frame,parameter=next(self.auto_iterator)
            self.parameter=parameter;self.integration_changed.emit(parameter)
            self.state.emit(f"自动积分 · 第 {step}/12 轮 · {frame}/3 帧 · 参数 {parameter}")
            self.auto_timer.start(0)
        except StopIteration as done:
            parameter,peak,steps,status=done.value;self.parameter=parameter
            reason={1:"光线过强，已到最小积分",2:"光线过弱，已到最大积分",3:"调整未收敛，请手动设置"}.get(status)
            message=(reason if reason else "自动完成")+f"：参数 {parameter}，峰值 {peak:.0f}，{steps} 次调整"
            self.finish_auto(message)
        except Exception as e:self.fail(e)

    def finish_auto(self,message,resume=None):
        if self.auto_timer:self.auto_timer.stop()
        if self.auto_iterator is not None:self.auto_iterator.close();self.auto_iterator=None
        if self.driver and self.driver.parameter is not None:self.parameter=self.driver.parameter
        self.integration_changed.emit(self.parameter)
        self.auto_done.emit(self.parameter,message)
        self.running=self.auto_resume if resume is None else resume
        if self.running and self.timer:self.timer.start()
        self.state.emit("连续采集中" if self.running else "已连接 · 自动积分结束")

    def fail(self,e):
        if self.auto_timer:self.auto_timer.stop()
        if self.auto_iterator is not None:self.auto_iterator.close();self.auto_iterator=None
        self.running=False;self.ready=False
        if self.timer:self.timer.stop();self.timer.deleteLater();self.timer=None
        if self.driver:self.driver.close();self.driver=None
        self.error.emit(str(e));self.state.emit("设备未连接")
    @Slot()
    def disconnect_device(self):
        self.stop()
        if self.driver:self.driver.close();self.driver=None
        if self.timer:self.timer.deleteLater();self.timer=None
        self.ready=False;self.state.emit("未连接")
