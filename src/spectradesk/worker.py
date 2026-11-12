from datetime import datetime, timezone
import time
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QThread
from .driver import Driver, DeviceDisconnectedError
from .camera import CameraDriver, CameraProfile, cameras

def choose_auto_average(single_frame_seconds, current_average):
    """Keep 1–20 Hz settings; slow groups use one frame, fast groups target 20 Hz."""
    current=max(1,min(8,int(current_average)))
    if not np.isfinite(single_frame_seconds) or single_frame_seconds<=0:return current
    period=max(.040,single_frame_seconds*current)  # acquisition timer interval
    if period>1:return 1
    if period<.050:
        return max(current,min(8,int(np.ceil(.050/single_frame_seconds))))
    return current


class Acquisition(QObject):
    connected=Signal(object)
    connection_changed=Signal(bool)
    device_available=Signal(bool)
    frame=Signal(object)
    capture_started=Signal(float,int,int)
    state=Signal(str)
    error=Signal(str)
    auto_done=Signal(int,str)
    integration_changed=Signal(int)
    average_changed=Signal(int)
    def __init__(self,demo=False):
        super().__init__();self.demo=demo;self.driver=None;self.timer=None;self.running=False;self.ready=False
        self.backend='fla5000';self.camera_path='';self.camera_profile=CameraProfile();self.camera_auto=True
        self.parameter=25;self.average=1;self.counter=0;self.auto_timer=None;self.auto_iterator=None;self.presence_timer=None;self.discovery_timer=None;self.available=None
    @Slot()
    def connect_device(self):
        try:
            if self.ready:return
            self.start_discovery()
            if not self.available:return
            if self.demo:
                self.wave=np.linspace(279,975,2048,dtype=np.float32)
                self.extra=((self.wave<365)|(self.wave>872)).astype(np.uint8)
                self.meta=dict(model="FLA5000 · 模拟",serial="DEMO",firmware="模拟数据",anchors=[])
                if self.backend=='camera':
                    self.wave,self.extra=self.camera_profile.wavelengths()
                    self.meta=dict(model='Camera · 模拟',serial='DEMO-CAMERA',firmware='模拟数据',backend='camera',camera_profile={})
            else:
                self.driver=CameraDriver(self.camera_path,self.camera_profile) if self.backend=='camera' else Driver();self.meta,self.wave,self.extra=self.driver.open()
                if self.backend=='camera':self.driver.set_exposure_auto(self.camera_auto)
            self.ready=True;self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.acquire)
            if not self.demo:
                self.presence_timer=QTimer(self);self.presence_timer.setInterval(750)
                self.presence_timer.timeout.connect(self.check_connection);self.presence_timer.start()
            self.connection_changed.emit(True)
            self.connected.emit(dict(meta=self.meta,wave=self.wave,extra=self.extra,demo=self.demo))
            self.state.emit("已连接 · 待采集")
        except Exception as e:self.fail(e)
    @Slot(object)
    def configure_backend(self,config):
        self.disconnect_device()
        self.backend=config['backend'];self.camera_path=config.get('path','');self.camera_profile=config.get('profile',CameraProfile())
        self.available=None;self.start_discovery()

    def publish_availability(self,available):
        available=bool(available)
        changed=self.available is None or self.available!=available
        self.available=available
        if changed:self.device_available.emit(available)
        return changed
    def start_discovery(self):
        if self.discovery_timer is None:
            self.discovery_timer=QTimer(self);self.discovery_timer.setInterval(750)
            self.discovery_timer.timeout.connect(self.scan_devices)
        self.discovery_timer.start();self.scan_devices()
    @Slot()
    def scan_devices(self):
        if self.ready or QThread.currentThread().isInterruptionRequested():return
        try:
            available=self.demo or (self.camera_path in cameras() if self.backend=='camera' else Driver.device_available())
            if self.publish_availability(available):
                self.state.emit('已找到光谱仪 · 未连接' if available else '未找到光谱仪')
        except Exception as e:
            if self.publish_availability(False):self.state.emit('设备检测失败：'+str(e))

    @Slot()
    def check_connection(self):
        if not self.ready or self.demo or self.driver is None or self.running or self.auto_iterator is not None:return
        try:self.driver.check_connected()
        except Exception as e:self.fail(e)

    def stop_presence_monitor(self):
        if self.presence_timer:
            self.presence_timer.stop();self.presence_timer.deleteLater();self.presence_timer=None

    @Slot(int,int,bool)
    def start(self,parameter,average,continuous):
        if not self.ready or self.auto_iterator is not None:return
        try:
            self.parameter=parameter;self.average=max(1,min(8,int(average)))
            if self.driver:self.driver.set_parameter(parameter)
            self.integration_changed.emit(parameter)
            self.running=continuous
            if continuous:self.timer.start()
            self.state.emit("连续采集中" if continuous else "单次采集中")
            self.acquire()
        except Exception as e:self.fail(e)
    @Slot(bool)
    def set_camera_auto(self,enabled):
        self.camera_auto=bool(enabled)
        if self.backend=='camera' and self.driver is not None:
            try:
                self.driver.set_exposure_auto(enabled)
                if not enabled:self.driver.set_parameter(self.parameter)
            except Exception as e:self.error.emit(str(e))
    @Slot(int)
    def set_average(self,average):
        # Queued on the acquisition thread: never split an in-flight group.
        self.average=max(1,min(8,int(average)))
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
            self.capture_started.emit(started,self.parameter,self.average)
            if self.demo:
                x=self.wave;signal=np.zeros_like(x,dtype=np.float64)
                for center,width,height in [(405,1.4,650),(436,1.2,3200),(487,4.3,900),(546,1.8,7200),(580,15,1000),(611,1.5,10500),(631,2,650)]:
                    signal+=height*np.exp(-.5*((x-center)/width)**2)
                counts=1965+signal*self.parameter/50
                rng=np.random.default_rng()
                frames=np.clip(32767-np.minimum(counts,16640)+rng.normal(0,12,(self.average,len(x))),0,65535).astype(np.uint16)
                if self.backend=='camera':
                    frames=np.clip(signal[None,:]/80+rng.normal(0,.1,(self.average,len(x))),0,255).astype(np.float32)
            else:frames=self.driver.capture(self.average)
            self.counter+=1
            payload=dict(wave=self.wave,extra=self.extra,adc_frames=frames,mean=32767-frames.mean(axis=0),parameter=self.parameter,average=self.average,utc=datetime.now(timezone.utc).isoformat(),elapsed=time.monotonic()-started,index=self.counter,device=self.meta,demo=self.demo)
            if self.backend=='camera':
                payload.update(mean=frames.mean(axis=0),intensity_unit='camera DN',backend='camera',camera_image=(np.zeros((self.camera_profile.height,self.camera_profile.width,3),dtype=np.uint8) if self.demo else self.driver.image),saturated=(False if self.demo else self.driver.saturated),wavelength_method='camera pixel calibration')
            if self.backend=='camera' and not self.demo:
                payload.update(camera_exposure_mode='spectrum-auto' if self.camera_auto else 'manual',camera_exposure_ms=getattr(self.driver,'exposure_used',self.parameter)/10)
                payload['parameter']=getattr(self.driver,'exposure_used',self.parameter)
            self.frame.emit(payload)
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
        if self.backend=='camera':return
        if not self.ready or self.auto_iterator is not None:return
        self.auto_resume=self.running;self.running=False
        if self.timer:self.timer.stop()
        self.auto_started=time.monotonic();self.auto_frame_times=[];self.auto_timing_parameter=None
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
            started=time.monotonic()
            step,frame,parameter=next(self.auto_iterator)
            duration=time.monotonic()-started
            if parameter!=self.auto_timing_parameter:
                self.auto_frame_times=[];self.auto_timing_parameter=parameter
            # The first frame also includes changing integration and prior-round
            # analysis. Measure only subsequent frames at the final setting.
            if frame>1:self.auto_frame_times.append(duration)
            self.parameter=parameter;self.integration_changed.emit(parameter)
            self.state.emit(f"自动积分 · 第 {step}/16 轮 · {frame}/3 帧 · 参数 {parameter}")
            self.auto_timer.start(0)
        except StopIteration as done:
            parameter,peak,steps,status=done.value;self.parameter=parameter
            reason={1:"光线过强，已到最小积分",2:"光线过弱，已到最大积分",3:"调整未收敛，请手动设置"}.get(status)
            message=(reason if reason else "自动完成")+f"：参数 {parameter}，峰值 {peak:.0f}，{steps} 次调整"
            if self.auto_frame_times and self.auto_timing_parameter==parameter:
                seconds=float(np.median(self.auto_frame_times))
                self.average=choose_auto_average(seconds,self.average)
                self.average_changed.emit(self.average)
                hz=1/max(.040,seconds*self.average)
                message+=f"，平均 {self.average} 帧，预计 {hz:.1f} Hz"
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
        self.stop_presence_monitor()
        if self.auto_timer:self.auto_timer.stop()
        if self.auto_iterator is not None:self.auto_iterator.close();self.auto_iterator=None
        self.running=False;self.ready=False
        if self.timer:self.timer.stop();self.timer.deleteLater();self.timer=None
        if self.driver:self.driver.close();self.driver=None
        self.publish_availability(False)
        self.connection_changed.emit(False)
        self.error.emit(str(e));self.state.emit("USB 已断开" if isinstance(e,DeviceDisconnectedError) else "设备未连接")
    @Slot()
    def disconnect_device(self):
        if QThread.currentThread().isInterruptionRequested() and self.discovery_timer:self.discovery_timer.stop()
        self.stop_presence_monitor()
        self.stop()
        if self.driver:self.driver.close();self.driver=None
        if self.timer:self.timer.deleteLater();self.timer=None
        self.ready=False;self.connection_changed.emit(False);self.state.emit("未连接")
