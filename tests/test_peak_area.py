import numpy as np
import pytest
from spectradesk.analysis import analyze,integrate_peak


def test_gaussian_area_with_background_and_nonuniform_sampling():
    x=np.linspace(400,700,3001);x+=.01*np.sin(x)
    y=2000+10000*np.exp(-.5*((x-550)/3)**2);before=y.copy()
    peak=analyze(x,y,400,700)[0];area=integrate_peak(x,y,peak,400,700)
    assert area.value==pytest.approx(10000*3*np.sqrt(2*np.pi),rel=.005)
    assert 539<area.start<542 and 558<area.end<561
    assert not area.warning and np.array_equal(y,before)


def test_truncated_area_is_not_reported_as_full_peak():
    x=np.linspace(400,700,3001);y=2000+10000*np.exp(-.5*((x-550)/3)**2)
    peak=analyze(x,y,549,551)[0];area=integrate_peak(x,y,peak,549,551)
    assert area.value is None and '范围' in area.warning


def test_overlapping_peaks_share_valley_not_double_count_whole_group():
    x=np.linspace(500,600,2001)
    y=500+3000*np.exp(-.5*((x-540)/3)**2)+2800*np.exp(-.5*((x-549)/3)**2)
    peaks=analyze(x,y,500,600)
    assert len(peaks)==2
    areas=[integrate_peak(x,y,p,500,600) for p in sorted(peaks,key=lambda p:p.wavelength)]
    assert all(a.value is not None for a in areas)
    assert areas[0].end<=areas[1].start+.1
    assert all('谷底' in a.warning for a in areas)


def test_clipped_peak_area_has_explicit_limit_warning():
    x=np.linspace(400,700,3001);y=np.minimum(2000+30000*np.exp(-.5*((x-550)/3)**2),16640)
    peak=analyze(x,y,400,700)[0];area=integrate_peak(x,y,peak,400,700)
    assert area.value is not None and '削顶' in area.warning
