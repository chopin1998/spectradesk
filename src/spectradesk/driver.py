import ctypes as C
import os
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
class Anchor(C.Structure):
    _fields_ = [("wavelength_nm", C.c_float), ("pixel", C.c_float)]
class Info(C.Structure):
    _fields_ = [("model", C.c_char*17), ("serial", C.c_char*17), ("firmware", C.c_char*17), ("anchor_count", C.c_uint), ("anchors", Anchor*32)]
class AutoResult(C.Structure):
    _fields_ = [("parameter", C.c_uint), ("iterations", C.c_uint), ("peak", C.c_float), ("status", C.c_int)]

class DeviceDisconnectedError(RuntimeError):
    pass

class Driver:
    def __init__(self):
        path = Path(os.environ.get("SPECTRADESK_DRIVER", ROOT / "native/libfla5000.so"))
        if not path.exists():
            raise RuntimeError("请先运行 make -C native 编译设备驱动")
        self.lib = C.CDLL(str(path)); self.handle = C.c_void_p()
        l = self.lib
        l.fla5000_open.argtypes = [C.POINTER(C.c_void_p), C.c_char_p]
        l.fla5000_close.argtypes = [C.c_void_p]
        l.fla5000_check_connected.argtypes = [C.c_void_p]
        l.fla5000_check_connected.restype = C.c_int
        l.fla5000_device_present.argtypes = []
        l.fla5000_device_present.restype = C.c_int
        l.fla5000_get_info.argtypes = [C.c_void_p]; l.fla5000_get_info.restype = C.POINTER(Info)
        l.fla5000_error_name.argtypes = [C.c_int]; l.fla5000_error_name.restype = C.c_char_p
        l.fla5000_set_integration_parameter.argtypes = [C.c_void_p, C.c_uint]
        l.fla5000_capture.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
        l.fla5000_wavelengths.argtypes = [C.POINTER(Info), C.POINTER(C.c_float), C.POINTER(C.c_uint8)]
        l.fla5000_auto.argtypes = [C.c_void_p, C.c_uint, C.c_float, C.POINTER(AutoResult)]
        self.parameter = None
    def check(self, result):
        if result:
            if result == -4: # LIBUSB_ERROR_NO_DEVICE
                raise DeviceDisconnectedError("USB 设备已断开，请插好光谱仪后重新连接。")
            name = self.lib.fla5000_error_name(result).decode()
            raise RuntimeError(f"设备通信失败：{name}。请确认 USB 已从虚拟机释放；异常后重新连接设备。")
    def open(self):
        self.check(self.lib.fla5000_open(C.byref(self.handle), None))
        try:
            info = self.lib.fla5000_get_info(self.handle).contents
            wave=(C.c_float*2048)(); extra=(C.c_uint8*2048)()
            self.check(self.lib.fla5000_wavelengths(C.byref(info), wave, extra))
            self.wave=np.ctypeslib.as_array(wave).copy(); self.extra=np.ctypeslib.as_array(extra).copy()
            self.meta={key: getattr(info,key).decode(errors="replace") for key in ("model","serial","firmware")}
            self.meta["anchors"]=[{"pixel":a.pixel,"wavelength_nm":a.wavelength_nm} for a in info.anchors[:info.anchor_count]]
            return self.meta, self.wave, self.extra
        except Exception:
            self.close(); raise
    @classmethod
    def device_available(cls):
        probe=cls()
        result=probe.lib.fla5000_device_present()
        if result<0:probe.check(result)
        return bool(result)
    def check_connected(self):
        self.check(self.lib.fla5000_check_connected(self.handle))
    def set_parameter(self, value):
        self.check(self.lib.fla5000_set_integration_parameter(self.handle, value)); self.parameter=value
    def capture(self, average):
        # Preserve all component frames for quality checks and reproducibility.
        frames=np.empty((average,2048),dtype=np.uint16)
        for frame in frames:
            self.check(self.lib.fla5000_capture(self.handle, frame.ctypes.data_as(C.POINTER(C.c_uint16))))
        return frames
    def auto_steps(self):
        """Yield after each USB frame so the worker can process cancellation."""
        parameter=self.parameter if self.parameter is not None else 25
        target=12000
        for step in range(1,13):
            self.set_parameter(parameter)
            frames=[]
            for frame in range(1,4):
                frames.append(self.capture(1)[0])
                yield step,frame,parameter
            mean=32767-np.mean(frames,axis=0)
            peak=float(np.max(mean[10:2041]))
            if abs(peak-target)<=target*.08:
                return parameter,peak,step,0
            baseline=float(np.mean(mean[10:70]))
            ratio=.5 if peak>=16500 else (target-baseline)/max(peak-baseline,1.)
            next_parameter=int(np.clip(np.floor(parameter*np.clip(ratio,.5,2.)+.5),15,1000))
            if next_parameter==parameter:
                return parameter,peak,step,1 if parameter==15 else (2 if parameter==1000 else 3)
            parameter=next_parameter
        return self.parameter,peak,12,3

    def auto(self):
        steps=self.auto_steps()
        while True:
            try:next(steps)
            except StopIteration as done:
                parameter,peak,count,status=done.value
                if status:
                    raise RuntimeError(f"自动积分未达到目标（状态 {status}，参数 {parameter}）；请调整光强或手动设置。")
                return parameter,peak,count
    def close(self):
        if self.handle:
            self.lib.fla5000_close(self.handle); self.handle=C.c_void_p()
