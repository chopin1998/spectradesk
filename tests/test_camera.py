import json
import numpy as np
import pytest
from spectradesk.camera import CameraProfile
from spectradesk.storage import save_measurement

def test_seller_roi_and_channel_weights():
    p=CameraProfile();assert p.roi()==(0,540,1920,43)
    image=np.zeros((1080,1920,3),dtype=np.uint8);image[540:583,0,2]=100
    y,sat=p.extract(image)
    assert y[-1]==pytest.approx(29.9,abs=1e-4);assert y[0]==0;assert not sat
    with pytest.raises(ValueError):p.extract(image[:100])

def test_fit_and_roundtrip(tmp_path):
    p=CameraProfile();res=p.fit([[100,400],[600,550],[1100,700]])
    assert np.max(np.abs(res))<1e-9
    p.save(tmp_path/'profile.json');q=CameraProfile.load(tmp_path/'profile.json')
    wave,extra=q.wavelengths();assert wave[600]==pytest.approx(550);assert extra[0] and not extra[600]
    with pytest.raises(ValueError):p.fit([[100,500],[100,600]])
    with pytest.raises(ValueError):p.fit([[100,500],[200,400]])

def test_camera_export(tmp_path):
    p=CameraProfile();wave,extra=p.wavelengths();y=np.ones(len(wave))*12
    f=dict(wave=wave,extra=extra,adc_frames=y[None,:],mean=y,backend='camera',camera_image=np.zeros((2,3,3),np.uint8),device={'camera_profile':{}},wavelength_method='camera pixel calibration')
    save_measurement(tmp_path/'test.npz',f,y,y,[],{})
    with np.load(tmp_path/'test.npz',allow_pickle=False) as d:
        assert json.loads(str(d['metadata']))['intensity_unit']=='camera DN'
        assert np.all(d['raw_gray_frames']==12);assert d['camera_image_bgr'].shape==(2,3,3)
    save_measurement(tmp_path/'test.csv',f,y,y,[],{})
    assert 'raw_gray_mean' in (tmp_path/'test.csv').read_text()

def test_worker_keeps_camera_gray_uninverted(monkeypatch):
    from spectradesk.worker import Acquisition
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    class Fake:
        saturated=False
        image=np.zeros((2,2,3),np.uint8)
        def capture(self,n):return np.tile(np.array([12.,30.,50.]),(n,1))
    worker=Acquisition();worker.backend='camera';worker.driver=Fake();worker.ready=True;worker.wave=np.array([400,500,600]);worker.extra=np.zeros(3);worker.meta={};worker.average=2
    frames=[];worker.frame.connect(frames.append);worker.acquire()
    np.testing.assert_array_equal(frames[0]['mean'],[12,30,50]);assert frames[0]['backend']=='camera'


@pytest.mark.parametrize("height,start,size", [(1080,50,4),(1080,17,7),(101,13,9),(100,0,10),(100,90,10)])
def test_theremino_bottom_up_dib_roi_matches_top_down_camera(height,start,size):
    # Model the observed Windows RGB24 positive-height DIB: first row is bottom.
    # Distinct rows/columns catch vertical reflection and off-by-one errors.
    p=CameraProfile(width=32,height=height,start_y=start,size_y=size)
    rng=np.random.default_rng(7)
    image=rng.integers(0,200,(height,32,3),dtype=np.uint8)
    dib=image[::-1,::-1]
    h=max(1,height*size//100);win_y=height-height*start//100-h
    strip=dib[win_y:win_y+h].astype(float)
    expected=(strip @ np.array([.114,.587,.299])).mean(axis=0)
    actual,_=p.extract(image)
    np.testing.assert_allclose(actual,expected,atol=3e-5,rtol=1e-6)


def test_camera_exposure_control_and_readback():
    from spectradesk.camera import CameraDriver
    from types import SimpleNamespace
    class Capture:
        def __init__(self):self.values={1:3,2:312}
        def set(self,key,value):self.values[key]=value;return True
        def get(self,key):return self.values[key]
    driver=CameraDriver('/dev/video-test',CameraProfile());driver.cap=Capture()
    driver.cv2=SimpleNamespace(CAP_PROP_AUTO_EXPOSURE=1,CAP_PROP_EXPOSURE=2)
    driver.set_exposure_auto(False);driver.set_parameter(400)
    assert driver.cap.values=={1:1,2:400}
    driver.set_exposure_auto(True);driver.set_parameter(500)
    assert driver.cap.values=={1:1,2:78}
    with pytest.raises(ValueError):
        driver.set_exposure_auto(False);driver.set_parameter(77)
    driver.cap.get=lambda key:999
    with pytest.raises(RuntimeError,match='未生效'):driver.set_exposure_auto(True)


@pytest.mark.parametrize('current,peak,expected',[(312,255,156),(78,255,78),(78,50,156),(100,195,100),(10000,10,10000)])
def test_spectrum_auto_exposure_policy(current,peak,expected):
    from spectradesk.camera import CameraDriver
    assert CameraDriver.auto_exposure_value(current,peak)==expected


def test_auto_meters_rgb_peak_and_changes_only_between_groups():
    from spectradesk.camera import CameraDriver
    from types import SimpleNamespace
    profile=CameraProfile(width=16,height=16)
    image=np.zeros((16,16,3),dtype=np.uint8);image[8,5,2]=255
    class Capture:
        def __init__(self):self.settings={1:1,2:156}
        def read(self):return True,image.copy()
        def set(self,k,v):self.settings[k]=v;return True
        def get(self,k):return self.settings[k]
    driver=CameraDriver('/dev/test',profile);driver.cap=Capture()
    driver.cv2=SimpleNamespace(CAP_PROP_AUTO_EXPOSURE=1,CAP_PROP_EXPOSURE=2)
    driver.exposure_value=156
    frames=driver.capture(2)
    assert driver.saturated and driver.exposure_used==156
    assert driver.exposure_value==78
    np.testing.assert_array_equal(frames[0],frames[1])
    assert frames.max()<80  # gray looks dim, but one RGB channel already clips


def test_single_line_offset_preserves_dispersion():
    p=CameraProfile();before,_=p.wavelengths();p.fit([[500,before[500]+3.2]],degree=0)
    after,_=p.wavelengths()
    np.testing.assert_allclose(after-before,3.2,atol=1e-10)
    np.testing.assert_allclose(np.diff(after),np.diff(before),atol=1e-10)


def test_auto_exposure_converges_with_brightness_changes():
    from spectradesk.camera import CameraDriver
    from types import SimpleNamespace
    p=CameraProfile(width=16,height=16)
    class Cap:
        def __init__(self):self.exposure=78;self.light=.5
        def read(self):
            image=np.zeros((16,16,3),dtype=np.uint8)
            image[8,:,1]=min(255,round(self.exposure*self.light))
            return True,image
        def set(self,key,value):self.exposure=value;return True
        def get(self,key):return self.exposure
    d=CameraDriver('/dev/test',p);d.cap=Cap();d.cv2=SimpleNamespace(CAP_PROP_EXPOSURE=1)
    for _ in range(8):d.capture(1)
    assert 170<=d.exposure_used*.5<=220
    previous=d.exposure_used
    d.cap.light=1.
    for _ in range(8):d.capture(1)
    assert d.exposure_used<previous and 170<=d.exposure_used<=220


def test_nonlinear_wavelength_strip_alignment_preserves_input():
    from spectradesk.camera import wavelength_aligned_strip
    rgb=np.zeros((2,5,3),dtype=np.uint8);rgb[:,2,0]=255
    original=rgb.copy();wave=np.array([400.,410.,430.,460.,500.])
    aligned,left,span=wavelength_aligned_strip(rgb,wave)
    centers=left+(np.arange(5)+.5)*span/5
    assert centers[np.argmax(aligned[0,:,0])]==425.
    np.testing.assert_array_equal(rgb,original)


def test_manual_capture_never_runs_saturation_controller():
    from spectradesk.camera import CameraDriver
    from spectradesk.worker import Acquisition
    from types import SimpleNamespace
    class Cap:
        def __init__(self):self.settings={1:1,2:78};self.writes=[]
        def set(self,key,value):self.settings[key]=value;self.writes.append((key,value));return True
        def get(self,key):return self.settings[key]
        def read(self):return True,np.full((16,16,3),255,dtype=np.uint8)
    d=CameraDriver('/dev/test',CameraProfile(width=16,height=16));d.cap=Cap()
    d.cv2=SimpleNamespace(CAP_PROP_AUTO_EXPOSURE=1,CAP_PROP_EXPOSURE=2)
    worker=Acquisition();worker.backend='camera';worker.driver=d;worker.ready=True;worker.parameter=400
    # Switch from auto to manual through the same slot used by the UI.
    worker.set_camera_auto(False)
    assert not d.exposure_auto and d.cap.settings[2]==400
    d.auto_exposure_value=lambda *_:(_ for _ in ()).throw(AssertionError('manual mode called auto controller'))
    writes=list(d.cap.writes)
    for _ in range(4):d.capture(2)
    assert d.cap.writes==writes and d.exposure_used==400 and d.saturated
    worker.set_integration(200)
    writes=list(d.cap.writes)
    d.capture(2)
    assert d.cap.writes==writes and d.exposure_used==200


def test_wavelength_calibration_comparison_modes():
    from spectradesk.camera import display_camera_profile
    p=CameraProfile();original=p.wavelengths()[0].copy()
    p.fit([[100,400],[700,550],[1500,800]],2)
    calibrated=display_camera_profile(p,True,True).wavelengths()[0]
    linear=display_camera_profile(p,True,False).wavelengths()[0]
    before=display_camera_profile(p,False).wavelengths()[0]
    np.testing.assert_array_equal(before,original)
    assert not np.allclose(linear,calibrated)
    np.testing.assert_array_equal(p.wavelengths()[0],calibrated)


def test_auto_exposure_respects_frame_interval_cap():
    from spectradesk.camera import CameraDriver
    assert CameraDriver.auto_exposure_value(300,30,333)==333
