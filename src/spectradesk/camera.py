"""Camera spectrometer: explicit geometry, immutable raw samples, wavelength fits."""
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import numpy as np

@dataclass
class CameraProfile:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    flip: bool = True
    start_x: int = 0
    end_x: int = 1000
    start_y: int = 50
    size_y: int = 4
    minimum: float = 287.5412
    maximum: float = 1057.944
    coefficients: list = field(default_factory=list)
    points: list = field(default_factory=list)
    source: str = '卖家 Theremino v3.1 参数 · 待实测验证'
    device: str = ''

    def validate(self):
        if not (16 <= self.width <= 8192 and 16 <= self.height <= 8192 and 1 <= self.fps <= 120):
            raise ValueError('图像尺寸或帧率无效')
        if not (0 <= self.start_x < self.end_x <= 1000 and 1 <= self.size_y <= 100 and 0 <= self.start_y <= 100-self.size_y):
            raise ValueError('取样区域无效：横向为千分比，纵向为百分比')
        if not (0 < self.minimum < self.maximum < 10000):raise ValueError('波长范围无效')
        if self.coefficients:
            if len(self.coefficients) not in (2,3) or not np.isfinite(self.coefficients).all():raise ValueError('校准系数无效')
            x=np.arange(self.width);w=np.polyval(self.coefficients,x)
            if not np.isfinite(w).all() or np.any(np.diff(w)<=0):raise ValueError('校准曲线必须在整个图像范围内单调递增，请检查方向和参考点')
        return self

    def roi(self):
        self.validate()
        x=self.width*self.start_x//1000;end=self.width*self.end_x//1000
        h=max(1,self.height*self.size_y//100)
        # Theremino v3.1 wraps a positive-height DirectShow RGB24 DIB
        # without reversing its bottom-up rows. Its H-start-height rectangle
        # therefore maps to start in OpenCV's top-down image coordinates.
        y=self.height*self.start_y//100
        return x,y,end-x,h

    def wavelengths(self):
        x,_,w,_=self.roi();pixels=np.arange(x,x+w,dtype=float)
        wave=np.polyval(self.coefficients,pixels) if self.coefficients else self.minimum+(self.maximum-self.minimum)*pixels/self.width
        extra=np.zeros(w,dtype=np.uint8)
        if self.points:
            lo,hi=np.min(np.array(self.points)[:,0]),np.max(np.array(self.points)[:,0]);extra=((pixels<lo)|(pixels>hi)).astype(np.uint8)
        return wave,extra

    def extract(self,bgr):
        if bgr.shape!=(self.height,self.width,3):raise ValueError(f'相机实际尺寸 {bgr.shape[:2]} 与校准尺寸不符，请重新设置或校准')
        image=bgr[:,::-1] if self.flip else bgr
        x,y,w,h=self.roi();roi=image[y:y+h,x:x+w]
        samples=roi.astype(np.float32) @ np.array([.114,.587,.299],dtype=np.float32)
        return samples.mean(axis=0),bool(np.any(roi>=250))

    @classmethod
    def from_ini(cls,path):
        raw=Path(path).read_bytes()
        for enc in ('utf-8-sig','gb18030','cp1252'):
            try:text=raw.decode(enc);break
            except UnicodeDecodeError:continue
        values=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
        values={k.strip():v.strip() for k,v in values.items()}
        required=('VideoSize','Flip','StartX','EndX','StartY','SizeY','MinNm','MaxNm')
        if any(k not in values for k in required):raise ValueError('不是完整的 Theremino v3.1 INI 文件')
        width,height=map(int,values['VideoSize'].lower().split('x'))
        p=cls(width=width,height=height,flip=values['Flip'].lower()=='true',source=f'Theremino v3.1 INI: {Path(path).name}')
        for key,attr in [('StartX','start_x'),('EndX','end_x'),('StartY','start_y'),('SizeY','size_y')]:setattr(p,attr,int(values[key]))
        p.minimum=float(values['MinNm']);p.maximum=float(values['MaxNm'])
        return p.validate()

    def fit(self,points,degree=1):
        a=np.asarray(points,dtype=float)
        if a.ndim!=2 or a.shape[1]!=2 or len(a)<degree+1 or degree not in (0,1,2) or not np.isfinite(a).all():raise ValueError('偏移至少1点、线性至少2点、二次至少3点')
        a=a[np.argsort(a[:,0])]
        if np.any(np.diff(a[:,0])<=0) or np.any(np.diff(a[:,1])<=0) or a[0,0]<0 or a[-1,0]>=self.width or np.any(a[:,1]<=0):raise ValueError('像素和波长必须递增、无重复，且像素位于图像内')
        if degree==0:
            c=np.asarray(self.coefficients or [(self.maximum-self.minimum)/self.width,self.minimum],dtype=float).copy()
            c[-1]+=float(np.mean(a[:,1]-np.polyval(c,a[:,0])))
        else:c=np.polyfit(a[:,0],a[:,1],degree)
        candidate=CameraProfile(**asdict(self));candidate.coefficients=c.tolist();candidate.points=a.tolist();candidate.source='用户多点波长校准';candidate.validate()
        self.coefficients=candidate.coefficients;self.points=candidate.points;self.source=candidate.source
        return np.polyval(c,a[:,0])-a[:,1]

    def save(self,path):
        self.validate();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(asdict(self),ensure_ascii=False,indent=2));tmp.replace(path)

    @classmethod
    def load(cls,path):return cls(**json.loads(Path(path).read_text())).validate()


def cameras():
    paths=list(Path('/dev/v4l/by-id').glob('*video-index0'))
    return sorted(map(str,paths or Path('/dev').glob('video*')))

def display_camera_profile(profile,enabled=True,quadratic=True):
    candidate=CameraProfile(**asdict(profile))
    if not enabled:candidate.coefficients=[];candidate.points=[]
    elif not quadratic and len(candidate.coefficients)==3:
        if len(candidate.points)<2:raise ValueError('缺少参考点，无法生成线性对照')
        points=np.asarray(candidate.points);candidate.coefficients=np.polyfit(points[:,0],points[:,1],1).tolist()
    return candidate.validate()

def wavelength_aligned_strip(rgb,wavelengths):
    """Resample only the display image onto a uniform calibrated wavelength grid."""
    wave=np.asarray(wavelengths,dtype=float)
    if rgb.ndim!=3 or rgb.shape[1]!=len(wave) or len(wave)<2 or np.any(np.diff(wave)<=0):raise ValueError('光带图像与波长坐标不匹配')
    uniform=np.linspace(wave[0],wave[-1],len(wave))
    result=np.empty_like(rgb)
    for row in range(rgb.shape[0]):
        for channel in range(3):result[row,:,channel]=np.rint(np.interp(uniform,wave,rgb[row,:,channel])).astype(np.uint8)
    step=uniform[1]-uniform[0]
    return result,float(uniform[0]-step/2),float(step*len(uniform))

class CameraDriver:
    def __init__(self,path,profile):self.path=path;self.profile=profile;self.cap=None;self.parameter=None;self.exposure_auto=True;self.exposure_value=78;self.exposure_used=78;self._exposure_changed=False
    def open(self):
        import cv2
        self.cv2=cv2
        if self.profile.device and self.profile.device!=self.path:raise ValueError('校准档案属于另一台相机；请重新选择相机并校准')
        self.cap=cv2.VideoCapture(self.path,cv2.CAP_V4L2)
        if not self.cap.isOpened():self.close();raise RuntimeError('无法打开相机；请先在 VirtualBox 中释放 Web Camera')
        self.cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,self.profile.width);self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,self.profile.height);self.cap.set(cv2.CAP_PROP_FPS,self.profile.fps);self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        # V4L2 starts/reinitializes the stream on the first read. Apply exposure
        # controls only after that transition, otherwise UVC may restore auto.
        ok,image=self.cap.read()
        if not ok:self.close();raise RuntimeError('相机启动取流失败')
        self.image=image.copy()
        self.wave,self.extra=self.profile.wavelengths()
        self.meta=dict(model='Camera · Theremino',serial=self.path,firmware='V4L2 / MJPG',backend='camera',camera_profile=asdict(self.profile))
        return self.meta,self.wave,self.extra
    def capture(self,average):
        frames=[];self.saturated=False
        if self._exposure_changed:
            for _ in range(2):
                ok,_image=self.cap.read()
                if not ok:raise RuntimeError('相机曝光切换后读取失败')
            self._exposure_changed=False
        self.exposure_used=self.exposure_value
        brightest=0
        for _ in range(average):
            ok,image=self.cap.read()
            if not ok:raise RuntimeError('相机读取失败或已断开')
            values,sat=self.profile.extract(image);frames.append(values);self.saturated|=sat;self.image=image.copy()
            oriented=image[:,::-1] if self.profile.flip else image
            x,y,w,h=self.profile.roi();brightest=max(brightest,int(oriented[y:y+h,x:x+w].max()))
        if self.exposure_auto:
            next_value=self.auto_exposure_value(self.exposure_used,brightest)
            if next_value!=self.exposure_value:self._write_exposure(next_value)
        return np.asarray(frames)
    @staticmethod
    def auto_exposure_value(current,brightest):
        if 170<=brightest<=220:return current
        ratio=float(np.clip(195/max(brightest,1),.5,2.))
        if brightest>=250:ratio=.5
        return int(np.clip(round(current*ratio),78,10000))
    def set_exposure_auto(self,enabled):
        self.exposure_auto=bool(enabled)
        if self.cap is None:return
        mode=1  # Both modes use hardware manual; software auto meters the ROI.
        if not self.cap.set(self.cv2.CAP_PROP_AUTO_EXPOSURE,mode):raise RuntimeError('相机不支持切换自动曝光')
        actual=int(round(self.cap.get(self.cv2.CAP_PROP_AUTO_EXPOSURE)))
        if actual!=mode:raise RuntimeError(f'相机曝光模式设置未生效：请求 {mode}，实际 {actual}')
        if enabled:self._write_exposure(78)
    def set_parameter(self,value):
        self.parameter=int(value)
        if self.cap is None or self.exposure_auto:return
        self._write_exposure(self.parameter)
    def _write_exposure(self,value):
        if not 78<=value<=10000:raise ValueError('曝光时间必须在 7.8–1000 ms')
        if not self.cap.set(self.cv2.CAP_PROP_EXPOSURE,value):raise RuntimeError('相机不支持手动曝光设置')
        actual=int(round(self.cap.get(self.cv2.CAP_PROP_EXPOSURE)))
        if abs(actual-value)>1:raise RuntimeError(f'相机曝光时间设置未生效：请求 {value}，实际 {actual}')
        self.exposure_value=actual;self._exposure_changed=True
    def check_connected(self):
        if not Path(self.path).exists():raise RuntimeError('相机已断开')
    def close(self):
        if self.cap is not None:self.cap.release();self.cap=None
