"""Analysis always consumes unsmoothed, optionally dark-corrected measurements."""
from dataclasses import dataclass, asdict
import numpy as np
from scipy.signal import find_peaks

@dataclass
class PeakArea:
    start: float | None = None
    end: float | None = None
    value: float | None = None
    baseline_start: float | None = None
    baseline_end: float | None = None
    warning: str = ""
    method: str = "unsmoothed-trapezoid;local-linear-background;1%-or-3sigma-boundary"

@dataclass
class Peak:
    wavelength: float
    intensity: float
    baseline: float
    fwhm: float | None
    left: float | None
    right: float | None
    warning: str = ""
    area: PeakArea | None = None


def analyze(wavelength, counts, start, stop, minimum_prominence=20):
    x, y = np.asarray(wavelength), np.asarray(counts)
    finite = np.isfinite(x) & np.isfinite(y)
    if not np.any(finite): return []
    baseline = float(np.percentile(y[finite], 10))
    noise_y = y[finite]
    mask = (x >= start) & (x <= stop) & np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 5 or np.any(np.diff(x) <= 0):
        return []
    amplitude = float(y.max() - baseline)
    noise = float(np.median(np.abs(np.diff(noise_y) - np.median(np.diff(noise_y)))) / .6745 / np.sqrt(2))
    if amplitude < max(minimum_prominence, 8 * noise):
        return []
    indices, properties = find_peaks(y, prominence=max(minimum_prominence, .035 * amplitude, 5 * noise))
    ranked = sorted(indices, key=lambda i: y[i], reverse=True)[:5]
    peaks = []
    for p in ranked:
        half = baseline + (y[p] - baseline) / 2
        l, r = p, p
        while l > 0 and y[l] > half:
            l -= 1
        while r < len(y)-1 and y[r] > half:
            r += 1
        valid = y[l] <= half and y[r] <= half and l < p < r
        left = right = width = None
        warning = ""
        if valid:
            left = float(x[l] + (half-y[l])/(y[l+1]-y[l])*(x[l+1]-x[l]))
            right = float(x[r-1] + (half-y[r-1])/(y[r]-y[r-1])*(x[r]-x[r-1]))
            width = right-left
            if any(l < q < r and q != p for q in ranked):
                warning = "重叠峰，宽度仅供参考"
        else:
            warning = "半高交点超出分析范围"
        if y[p] >= 16500:
            width = None
            warning = "峰顶可能削顶，半高宽无效"
        peaks.append(Peak(float(x[p]), float(y[p]), baseline, width, left, right, warning))
    return peaks


def display_smooth(y, count, method="STA"):
    """Display-only filters; never modify input measurement."""
    x = np.asarray(y, dtype=np.float64)
    if count == 0:
        return x.copy()
    n = int(count)
    if n < 1 or n > 250 or 2*n >= len(x):
        raise ValueError("Invalid smoothing count")
    if method == "STA":
        # Verified SDK kernel: [i-N,i+N), with original-value edge extension.
        sums = np.concatenate(([0.], np.cumsum(x)))
        out = np.empty_like(x)
        out[n:-n] = (sums[2*n:len(x)] - sums[:len(x)-2*n])/(2*n)
        out[:n], out[-n:] = x[n], x[-n]
        return out
    sums = np.concatenate(([0.], np.cumsum(x)))
    indices = np.arange(len(x)); lo = np.maximum(0, indices-n); hi = np.minimum(len(x), indices+n+1)
    return (sums[hi]-sums[lo])/(hi-lo)


def integrate_peak(wavelength,counts,peak,start,stop):
    """Local-baseline area of an automatically bounded peak, in counts*nm.

    A light filter locates boundaries only. Integration uses the original
    unsmoothed values. Overlapping peaks are divided at their intervening valley.
    """
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import peak_prominences
    x=np.asarray(wavelength,dtype=float);raw=np.asarray(counts,dtype=float)
    mask=(x>=start)&(x<=stop)
    x,raw=x[mask],raw[mask]
    if len(x)<5 or not np.isfinite(x).all() or not np.isfinite(raw).all() or np.any(np.diff(x)<=0):
        return PeakArea(warning='分析范围或数据无效')
    smooth=gaussian_filter1d(raw,1.)
    p=int(np.argmin(abs(x-peak.wavelength)))
    if p==0 or p==len(x)-1:return PeakArea(warning='峰位接近分析边界')
    maxima,_=find_peaks(smooth)
    nearby=maxima[np.abs(maxima-p)<=2]
    if not len(nearby):return PeakArea(warning='峰位附近未找到局部极大值')
    p=int(nearby[np.argmax(smooth[nearby])])
    prominence,lb,rb=peak_prominences(smooth,[p])
    left,right=int(lb[0]),int(rb[0])
    if prominence[0]<=0 or left==p or right==p:return PeakArea(warning='未找到可靠峰边界')
    difference=np.diff(raw)
    noise=float(np.median(abs(difference-np.median(difference)))/.6745/np.sqrt(2))
    candidates,_=find_peaks(smooth,prominence=max(20.,.03*prominence[0],5*noise))
    before=candidates[candidates<p-2];after=candidates[candidates>p+2]
    lower,upper=0,len(x)-1
    neighbors=[]
    if len(before):
        lower=int(before[-1])+int(np.argmin(smooth[before[-1]:p+1]));neighbors.append(int(before[-1]))
    if len(after):
        upper=p+int(np.argmin(smooth[p:after[0]+1]));neighbors.append(int(after[0]))
    # A valley between peaks is a shared boundary, not a background anchor.
    if neighbors:
        _,neighbor_left,neighbor_right=peak_prominences(smooth,neighbors)
        left=min(left,int(min(neighbor_left)));right=max(right,int(max(neighbor_right)))
    baseline=np.interp(x,[x[left],x[right]],[smooth[left],smooth[right]])
    signal=smooth-baseline
    height=float(signal[p]);threshold=max(.01*height,3*noise)
    edge_limit=peak.baseline+max(.03*height,5*noise)
    if (left==0 and smooth[0]>edge_limit) or (right==len(x)-1 and smooth[-1]>edge_limit):
        return PeakArea(warning='峰被分析范围截断，扩大范围后重试')
    if height<=threshold:return PeakArea(warning='信噪比不足，无法确定积分边界')
    l=r=p
    while l>lower and signal[l]>threshold:l-=1
    while r<upper and signal[r]>threshold:r+=1
    warnings=[]
    left_ok=signal[l]<=threshold or lower>0
    right_ok=signal[r]<=threshold or upper<len(x)-1
    if not left_ok or not right_ok:
        return PeakArea(start=float(x[l]) if left_ok else None,end=float(x[r]) if right_ok else None,warning='峰未回落至背景，扩大分析范围后重试')
    if (l==lower and lower>0 and signal[l]>threshold) or (r==upper and upper<len(x)-1 and signal[r]>threshold):
        warnings.append('相邻峰按谷底分界，未作分峰拟合')
    if '削顶' in peak.warning:warnings.append('削顶，面积仅为下限估计')
    area=float(np.trapezoid(raw[l:r+1]-baseline[l:r+1],x[l:r+1]))
    return PeakArea(float(x[l]),float(x[r]),area,float(baseline[l]),float(baseline[r]),'；'.join(warnings))
