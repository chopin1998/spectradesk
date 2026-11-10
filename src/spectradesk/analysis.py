"""Analysis always consumes unsmoothed, optionally dark-corrected measurements."""
from dataclasses import dataclass, asdict
import numpy as np
from scipy.signal import find_peaks

@dataclass
class Peak:
    wavelength: float
    intensity: float
    baseline: float
    fwhm: float | None
    left: float | None
    right: float | None
    warning: str = ""


def analyze(wavelength, counts, start, stop):
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
    if amplitude < max(20, 8 * noise):
        return []
    indices, properties = find_peaks(y, prominence=max(20, .035 * amplitude, 5 * noise))
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
