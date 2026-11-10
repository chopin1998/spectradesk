import csv,json,os,tempfile
from pathlib import Path
import numpy as np
from dataclasses import asdict

def save_measurement(path, frame, corrected, displayed, peaks, settings, dark=None):
    path=Path(path)
    metadata={k:v for k,v in frame.items() if k not in ('wave','extra','adc_frames','mean')}
    metadata.update(schema="spectradesk/1",settings=settings,peaks=[asdict(p) for p in peaks],analysis_source="unsmoothed_corrected_counts",intensity_unit="ADC counts",wavelength_method="device-anchor piecewise linear",dark_applied=dark is not None or settings.get('calibration',{}).get('method')=='sta-mode1-v1',dark_source='manual' if dark is not None else ('device-template' if settings.get('calibration',{}).get('method')=='sta-mode1-v1' else 'none'))
    # A single-file NPZ is the authoritative, lossless measurement record.
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.spectradesk-',suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f:
            if path.suffix.lower()=='.csv':
                import io
                text=io.TextIOWrapper(f,encoding='utf-8',newline='',write_through=True)
                text.write('# '+json.dumps(metadata,ensure_ascii=False)+'\n')
                writer=csv.writer(text);writer.writerow(['pixel','wavelength_nm','extrapolated','adc_mean','mean_counts','corrected_counts','display_counts'])
                for i,x in enumerate(frame['wave']):writer.writerow([i,float(x),int(frame['extra'][i]),float(32767-frame['mean'][i]),float(frame['mean'][i]),float(corrected[i]),float(displayed[i])])
                text.flush();text.detach()
            else:
                np.savez_compressed(f,metadata=json.dumps(metadata,ensure_ascii=False),wavelength_nm=frame['wave'],extrapolated=frame['extra'],adc_frames=frame['adc_frames'],mean_counts=frame['mean'],corrected_counts=corrected,display_counts=displayed,dark_counts=np.array([]) if dark is None else dark)
        os.replace(tmp,path)
    except Exception:
        if os.path.exists(tmp):os.unlink(tmp)
        raise
