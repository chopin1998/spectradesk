"""Device-bound calibration recovered from STA and checked against USB captures.

Raw ADC remains immutable. This module never writes calibration to hardware.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import numpy as np
from .analysis import display_smooth

@dataclass(frozen=True)
class CalibrationProfile:
    data: dict
    sha256: str

    @property
    def serial(self): return self.data['serial']

    @classmethod
    def read(cls, path):
        content=Path(path).read_bytes();d=json.loads(content)
        if d.get('schema')!='spectradesk-calibration/1':raise ValueError('不支持的校准文件格式')
        zero=np.asarray(d['zero_counts'],dtype=float)
        anchors=np.asarray([[a['pixel'],a['wavelength_nm']] for a in d['anchors']],dtype=float)
        segments=np.asarray(d['nonlinearity'],dtype=float)
        if zero.shape!=(2048,) or not np.isfinite(zero).all() or not 0<zero[5:70].mean()<65535:raise ValueError('暗背景模板无效')
        if anchors.ndim!=2 or anchors.shape[1]!=2 or len(anchors)<2 or not np.isfinite(anchors).all() or not (np.diff(anchors,axis=0)>0).all():raise ValueError('波长标定无效')
        if segments.ndim!=2 or segments.shape[1]!=5 or not len(segments) or not np.isfinite(segments).all() or np.any(segments[:,0]>=segments[:,1]) or np.any(np.diff(segments[:,0])<0):raise ValueError('非线性系数无效')
        return cls(d,hashlib.sha256(content).hexdigest())

    def matches(self,device):
        if any(device.get(k)!=self.data[k] for k in ('serial','model','firmware')):return False
        a=device.get('anchors',[]);b=self.data['anchors']
        return len(a)==len(b) and all(abs(x['pixel']-y['pixel'])<.001 and abs(x['wavelength_nm']-y['wavelength_nm'])<.001 for x,y in zip(a,b))


def profile_for(device):
    # Explicit inventory prevents a serial number from being interpreted as a path.
    if device.get('serial')!='201506192':return None
    p=CalibrationProfile.read(Path(__file__).with_name('data')/'201506192.json')
    return p if p.matches(device) else None


def nonlinear_correct(values, profile):
    x=np.asarray(values,dtype=float);out=x.copy();done=np.zeros(x.shape,dtype=bool)
    segments=profile.data['nonlinearity']
    for k,(lo,hi,a,b,c) in enumerate(segments):
        selected=(x>lo)&(x<hi)
        if k==0:selected|=x<=hi
        elif k==len(segments)-1:selected|=x>=lo
        else:selected&=x<segments[-1][0]
        selected&=~done
        out[selected]=(x[selected]*x[selected])*c+x[selected]*b+a
        done|=selected
    return out


def correct_counts(mean_counts, profile, *, nonlinear=True, manual_dark=None):
    raw=np.array(mean_counts,dtype=float,copy=True)
    if raw.shape!=(2048,) or not np.isfinite(raw).all():raise ValueError('光谱必须包含2048个有限数值')
    raw[:10]=raw[10];raw[-7:]=raw[-8]
    if manual_dark is not None:
        dark=np.array(manual_dark,dtype=float,copy=True)
        if dark.shape!=raw.shape or not np.isfinite(dark).all():raise ValueError('手动暗背景无效')
        dark[:10]=dark[10];dark[-7:]=dark[-8]
        y=raw-dark
        if nonlinear:y=nonlinear_correct(y,profile)
        return y,dict(method='manual-dark-then-nonlinearity',profile_sha256=profile.sha256,nonlinearity=bool(nonlinear),manual_dark=True)
    zero=np.asarray(profile.data['zero_counts'],dtype=float)
    # SDK mode 1: scale the pixelwise template using [start,end), not an offset.
    first_scale=float(raw[5:70].mean()/zero[5:70].mean())
    reference=zero*first_scale
    restored=nonlinear_correct(raw-reference,profile)+reference if nonlinear else raw
    # STA's wave-data path repeats auto-dark after the nonlinear stage.
    second_scale=float(restored[5:70].mean()/zero[5:70].mean())
    return restored-zero*second_scale,dict(method='sta-mode1-v1',profile_sha256=profile.sha256,nonlinearity=bool(nonlinear),manual_dark=False,initial_dark_scale=first_scale,final_dark_scale=second_scale,dark_pixels=[5,70],edge_fill=[10,7])


def sta_smooth(values,count):
    y=np.asarray(values,dtype=float).copy()
    # SDK passes 0x7e4 (2020), leaving the last 28 pixels unsmoothed.
    y[:2020]=display_smooth(y[:2020],count)
    return y


def sta_resample(values,profile,wavelength_nm):
    y=np.asarray(values,dtype=float);w=np.asarray(wavelength_nm,dtype=float)
    if y.shape!=(2048,) or not np.isfinite(y).all() or not np.isfinite(w).all():raise ValueError('重采样数据无效')
    a=profile.data['anchors'];nm=np.array([a['wavelength_nm'] for a in a]);px=np.array([a['pixel'] for a in a])
    segment=np.clip(np.searchsorted(nm,w,side='right')-1,0,len(nm)-2)
    position=px[segment]+(w-nm[segment])*(px[segment+1]-px[segment])/(nm[segment+1]-nm[segment])
    j=np.floor(position).astype(int)
    if np.any(j<0) or np.any(j+2>=2048):raise ValueError('请求波长超出三点插值的有效像素范围')
    q=position-j
    return y[j]*(q-1)*(q-2)/2-y[j+1]*q*(q-2)+y[j+2]*q*(q-1)/2


def save_sta_csv(path,frame,profile,corrected,smooth_count):
    """Explicit comparison export. Native NPZ retains all pixels and ADC frames."""
    import csv,io,os,tempfile
    w=np.arange(280.,973.);v=sta_resample(sta_smooth(corrected,smooth_count),profile,w)
    path=Path(path);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.sta-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f)
            writer.writerows([['SpectraDesk STA 对照导出'],['UTC',frame['utc']],['序列号',profile.serial],['积分参数',frame['parameter']],['实际平均帧数',len(frame['adc_frames'])],['平滑次数',smooth_count],['校准SHA256',profile.sha256],['波长(nm)','数值']])
            writer.writerows(zip(w.astype(int),np.rint(v).astype(int)))
        os.replace(tmp,path)
    except Exception:
        if os.path.exists(tmp):os.unlink(tmp)
        raise
