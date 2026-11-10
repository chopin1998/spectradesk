import numpy as np
from spectradesk.analysis import analyze,display_smooth

def test_gaussian_fwhm_with_offset():
    x=np.linspace(400,700,3001);y=2000+10000*np.exp(-.5*((x-550)/3)**2)
    p=analyze(x,y,400,700)[0]
    assert abs(p.wavelength-550)<.11
    assert abs(p.fwhm-2.354820045*3)<.01

def test_truncated_and_clipped_are_not_reported_as_good_widths():
    x=np.linspace(400,700,3001);y=2000+10000*np.exp(-.5*((x-550)/3)**2)
    p=analyze(x,y,549,551)[0];assert p.fwhm is None
    p=analyze(x,np.minimum(y*2,16640),400,700)[0];assert p.fwhm is None and '削顶' in p.warning

def test_flat_and_invalid_ranges():
    x=np.arange(2048);assert not analyze(x,np.ones(2048)*2000,0,2047)
    assert not analyze(x,x,1000,500)

def test_smoothing_preserves_input_and_sta_kernel():
    y=np.arange(2048,dtype=float);original=y.copy();z=display_smooth(y,5)
    assert np.array_equal(y,original)
    assert z[100]==99.5 and z[0]==5 and z[-1]==2043
    assert np.array_equal(display_smooth(y,0),y)

def test_display_smoothing_never_changes_analysis_input():
    x=np.linspace(400,700,2048);y=2000+9000*np.exp(-.5*((x-550)/1)**2)
    before=analyze(x,y,400,700)[0];display_smooth(y,30)
    assert analyze(x,y,400,700)[0]==before
