import numpy as np
import pytest
from spectradesk.camera_calibration import suggest_peak_pairs

def test_peak_suggestions_recover_offset_without_using_peak_heights():
    px=np.arange(1000.);wave=400+px*.25;indices=np.array([40,180,370,560,780,940])
    rx=np.linspace(380,680,2000);g=np.zeros_like(px);ry=np.zeros_like(rx)
    for i,height,reference_height in zip(indices,[80,120,70,150,100,130],[200,50,900,70,500,110]):
        g+=height*np.exp(-.5*((px-i)/2)**2)
        ry+=reference_height*np.exp(-.5*((rx-wave[i])/.35)**2)
    points,res=suggest_peak_pairs(px,g,wave+8,rx,ry)
    assert len(points)>=4 and np.max(np.abs(res))<.2
    np.testing.assert_allclose(points[:,1],400+points[:,0]*.25,atol=.15)

def test_automatic_pairing_rejects_insufficient_spectral_information():
    x=np.linspace(400,700,500)
    with pytest.raises(ValueError,match='不足4'):
        suggest_peak_pairs(np.arange(500),np.zeros(500),x,x,np.zeros(500))
