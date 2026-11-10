import csv,json
from pathlib import Path
import numpy as np
import pytest
from spectradesk.calibration import CalibrationProfile,profile_for,correct_counts,sta_smooth,sta_resample,nonlinear_correct,save_sta_csv

DATA=Path(__file__).parents[1]/'src/spectradesk/data/201506192.json'
FIX=Path(__file__).parent/'fixtures'
def profile():return CalibrationProfile.read(DATA)

@pytest.mark.parametrize('name',['250-1','250-2','500-1','500-2'])
def test_same_capture_reconstructs_all_sta_exported_points(name):
    p=profile();d=np.load(FIX/f'sync-{name}-usb.npz');raw=d['raw_counts_frames'].mean(0);original=raw.copy()
    corrected,meta=correct_counts(raw,p)
    rows=list(csv.reader((FIX/f'sync-{name}.csv').open(encoding='utf-8-sig')));i=next(i for i,r in enumerate(rows) if r and r[0]=='波长(nm)')
    x,expected=np.array([[float(r[0]),float(r[1])] for r in rows[i+1:] if len(r)>1]).T
    measured=sta_resample(sta_smooth(corrected,1),p,x)
    error=measured-expected
    assert np.max(abs(error))<.6
    assert np.sqrt(np.mean(error**2))<.32
    assert np.max(abs(np.rint(measured)-expected))<=1
    assert np.array_equal(raw,original)
    assert meta['initial_dark_scale']>0


def test_profile_rejects_other_device_or_changed_calibration():
    p=profile();dev={k:p.data[k] for k in ['serial','model','firmware','anchors']}
    assert profile_for(dev) is not None
    assert profile_for(dict(dev,serial='other')) is None
    assert profile_for(dict(dev,firmware='VER8')) is None
    assert profile_for(dict(dev,anchors=[])) is None


def test_invalid_profile_and_input_fail_closed(tmp_path):
    d=profile().data.copy();d['zero_counts']=[0]*2048;path=tmp_path/'bad.json';path.write_text(json.dumps(d))
    with pytest.raises(ValueError):CalibrationProfile.read(path)
    with pytest.raises(ValueError):correct_counts(np.full(2048,np.nan),profile())
    with pytest.raises(ValueError):sta_resample(np.ones(2048),profile(),[2000])


def test_nonlinearity_overlap_and_extrapolation_rules():
    p=profile();x=np.array([-10.,0.,2010.,10000.,11000.,35000.]);y=nonlinear_correct(x,p)
    for i in [0,1,2]:
        _,_,a,b,c=p.data['nonlinearity'][0];assert y[i]==pytest.approx(a+b*x[i]+c*x[i]**2)
    for i in [3,4,5]:
        _,_,a,b,c=p.data['nonlinearity'][-1];assert y[i]==pytest.approx(a+b*x[i]+c*x[i]**2)


def test_manual_dark_replaces_auto_dark_and_nonlinearity_can_be_disabled():
    p=profile();raw=np.full(2048,2500.);dark=np.full(2048,1900.)
    y,meta=correct_counts(raw,p,nonlinear=False,manual_dark=dark)
    assert np.all(y==600) and meta['manual_dark']
    assert np.all(dark==1900)
    ramp=np.arange(2048,dtype=float);sm=sta_smooth(ramp,1)
    assert np.array_equal(sm[2020:],ramp[2020:]) and sm[100]==99.5


def test_sta_export_is_explicit_about_actual_frames(tmp_path):
    p=profile();f=dict(utc='test',parameter=250,adc_frames=np.zeros((2,2048),dtype=np.uint16))
    path=tmp_path/'sta.csv';save_sta_csv(path,f,p,np.ones(2048),1)
    text=path.read_text(encoding='utf-8-sig')
    assert '实际平均帧数,2' in text and '校准SHA256,' in text
    assert len(text.splitlines())==701
