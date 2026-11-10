import json,numpy as np
from spectradesk.storage import save_measurement

def frame():
    adc=np.arange(2048,dtype=np.uint16)[None,:]
    return dict(wave=np.linspace(300,900,2048),extra=np.zeros(2048,dtype=np.uint8),adc_frames=adc,mean=32767-adc.mean(0),device={'serial':'test'},parameter=25,average=1,demo=True,utc='2026-11-10T00:00:00+00:00')

def test_roundtrip_preserves_raw_and_metadata(tmp_path):
    f=frame();y=f['mean'];p=tmp_path/'test.npz'
    save_measurement(p,f,y,y,[],{'smooth_count':0})
    with np.load(p,allow_pickle=False) as d:
        assert np.array_equal(d['adc_frames'],f['adc_frames'])
        assert json.loads(str(d['metadata']))['device']['serial']=='test'
        assert d['dark_counts'].size==0

def test_csv_does_not_mix_metadata_into_values(tmp_path):
    f=frame();p=tmp_path/'test.csv';save_measurement(p,f,f['mean'],f['mean'],[],{})
    lines=p.read_text().splitlines();assert lines[0].startswith('# ')
    assert len(lines)==2050 and lines[1].startswith('pixel,wavelength_nm')
