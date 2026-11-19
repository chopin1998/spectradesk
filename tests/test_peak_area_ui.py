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


def test_peak_table_splitter_sorting_and_manual_rows(tmp_path):
    script='''
import sys
from argparse import Namespace
import numpy as np
from PySide6 import QtCore,QtWidgets as W
from spectradesk.app import Window
app=W.QApplication([])
win=Window(Namespace(demo=True,connect=False,smoke=None,renderer='raster'));win.show()
errors=[]
def verify():
    try:
        assert isinstance(win.main_splitter,W.QSplitter)
        assert win.main_splitter.orientation()==QtCore.Qt.Orientation.Vertical
        assert win.main_splitter.count()==2

        x=np.linspace(500,600,2001)
        y=500+3000*np.exp(-.5*((x-530)/2)**2)+1500*np.exp(-.5*((x-570)/3)**2)
        win.range_start.setValue(500);win.range_end.setValue(600)
        win.display_start.setValue(500);win.display_end.setValue(600)
        win.frame_data=dict(wave=x,mean=y,extra=np.zeros(2001),adc_frames=(32767-y).astype(np.uint16)[None,:],parameter=250,average=1,demo=True,device=dict(serial='test'),index=1,elapsed=.1,utc='test')
        win.render();app.processEvents()

        # Sort by wavelength ascending (col 0) then descending
        win.on_peak_header_clicked(0)
        assert float(win.table.item(0,0).text())<float(win.table.item(1,0).text())
        win.on_peak_header_clicked(0)
        assert float(win.table.item(0,0).text())>float(win.table.item(1,0).text())

        # Add manual peak range [560, 580] -> finds peak near 570 nm
        win.manual_ranges.append((560.0,580.0))
        win.render();app.processEvents()
        assert win.table.rowCount()==3
        manual_rows=[r for r,(_,idx) in enumerate(win._table_rows) if idx is not None]
        auto_rows=[r for r,(_,idx) in enumerate(win._table_rows) if idx is None]
        assert len(manual_rows)==1 and len(auto_rows)==2
        mr=manual_rows[0];ar=auto_rows[0]
        assert abs(float(win.table.item(mr,0).text())-570.0)<0.2
        assert float(win.table.item(mr,5).text().replace(',',''))>0
        assert win.table.item(mr,0).background().style()!=QtCore.Qt.BrushStyle.NoBrush
        assert win.table.item(ar,0).background().style()==QtCore.Qt.BrushStyle.NoBrush

        # Inline edit manual end bound (col 4) and verify re-evaluation
        win.table.item(mr,4).setText('578.0')
        app.processEvents()
        assert win.manual_ranges[0]==(560.0,578.0)

        # Select manual row, verify highlight on main plot, then delete it
        win.table.selectRow(mr)
        app.processEvents()
        assert win.remove_manual_peak_btn.isEnabled()
        assert win.selected_region.isVisible() and win.selected_curve.isVisible() and win.selected_marker.isVisible()
        assert len(win.selected_curve.xData)>=2
        win.remove_selected_manual_peak()
        app.processEvents()
        assert win.table.rowCount()==2 and not win.manual_ranges
        win.table.clearSelection()
        app.processEvents()
        assert not win.selected_region.isVisible() and not win.selected_curve.isVisible()
    except BaseException as error:errors.append(error)
    finally:win.close();app.quit()
QtCore.QTimer.singleShot(400,verify);app.exec()
if errors:raise errors[0]
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
