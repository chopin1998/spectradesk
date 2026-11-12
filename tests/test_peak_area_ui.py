import os
import subprocess
import sys


def test_all_peak_areas_update_and_export_without_toggles(tmp_path):
    script='''
import sys,json
from argparse import Namespace
from pathlib import Path
import numpy as np
from PySide6 import QtCore,QtTest,QtWidgets as W
from spectradesk.app import Window
from spectradesk.storage import save_measurement
app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'));win.show()
errors=[]
def frame(first,second,shift=0):
    x=np.linspace(500,600,2001);y=500+first*np.exp(-.5*((x-530-shift)/2)**2)+second*np.exp(-.5*((x-570)/2)**2)
    return dict(wave=x,mean=y,extra=np.zeros(2001),adc_frames=(32767-y).astype(np.uint16)[None,:],parameter=250,average=1,demo=True,device=dict(serial='test'),index=1,elapsed=.1,utc='test')
def verify():
    try:
        win.range_start.setValue(500);win.range_end.setValue(600)
        win.display_start.setValue(500);win.display_end.setValue(600)
        win.frame_data=frame(3000,2000);win.render();app.processEvents()
        assert win.table.columnCount()==6
        assert all(win.table.horizontalHeaderItem(i).text() not in ('质量提示','积分') for i in range(6))
        assert all(win.table.item(0,i).textAlignment()==QtCore.Qt.AlignmentFlag.AlignCenter for i in range(6))
        assert all(p.area is not None and p.area.value>0 for p in win.peaks)
        assert win.table.item(0,3).text()!='—' and win.table.item(0,5).text()!='—'
        original_area=win.peaks[0].area.value;win.smooth.setValue(15)
        assert win.peaks[0].area.value==original_area
        assert len(win.area_starts.getData()[0])==2
        win.frame_data=frame(2000,3000,.2);win.render()
        assert all(p.area.value>0 for p in win.peaks)
        assert win.peaks[1].area.start<530.2<win.peaks[1].area.end
        path=Path(sys.argv[1])/'area.npz'
        save_measurement(path,win.frame_data,win.corrected,win.displayed,win.peaks,win.settings())
        with np.load(path) as data:meta=json.loads(str(data['metadata']))
        assert meta['peaks'][1]['area']['value']>0
        assert meta['peaks'][1]['area']['start']==win.peaks[1].area.start
        assert meta['peaks'][0]['area']['value']>0
        win.frame_data=frame(0,0);win.render()
        assert not win.peaks and len(win.area_starts.getData()[0])==0
        win.frame_data=frame(2000,3000,.2);win.render()
        assert all(p.area.value>0 for p in win.peaks)
        assert len(win.area_starts.getData()[0])==2
    except BaseException as error:errors.append(error)
    finally:win.close();app.quit()
QtCore.QTimer.singleShot(400,verify);app.exec()
if errors:raise errors[0]
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
