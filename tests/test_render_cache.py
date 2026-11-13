"""State changes without a new acquisition must reach every spectrum view."""
import os
import subprocess
import sys
import pytest


def run_ui(code, tmp_path):
    result=subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_CONFIG_HOME=str(tmp_path),
                 PYTHONDONTWRITEBYTECODE='1'), timeout=20)
    assert result.returncode==0, result.stdout+result.stderr


@pytest.mark.parametrize('change', ['analysis_range', 'camera_dark'])
def test_paused_processing_updates_comparison(change, tmp_path):
    run_ui("""
from argparse import Namespace
from unittest.mock import patch
import numpy as np
from PySide6 import QtWidgets as W
from spectradesk.workbench import Workbench
app=W.QApplication([])
w=Workbench(Namespace(demo=True, connect=False, smoke=None, renderer='raster'))
w.timer.stop()
for s in w.sessions:
    s._startup_timer.stop()
    s.device_present=True
try:
    change=CHANGE
    index=int(change=='camera_dark');s=w.sessions[index]
    x=np.linspace(400,700,2048);y=100+1000*np.exp(-.5*((x-550)/3)**2)
    frame=dict(wave=x, mean=y, extra=np.zeros(2048),
        adc_frames=np.full((2,2048),32760,dtype=np.uint16), parameter=3000,
        average=2, demo=True, device=dict(serial='test'), index=1, elapsed=.04,
        backend='camera' if index else 'fla5000')
    s.frame_data=frame;s.render();w.tabs.setCurrentIndex(2);w.refresh()
    name=('FLA5000','摄像头')[index]
    assert w.plot._series[name]['spec']['peaks']
    if change=='analysis_range':
        s.range_start.setValue(600);s.range_end.setValue(690)
    else:
        s.dark=dict(counts=np.full(2048,100.))
    s.render();w.refresh()
    assert s.frame_data is frame and frame['index']==1
    for plot in (w.plot,w.parallel_plots[index]):
        actual=plot._series[name]['spec']['peaks']
        assert [p.wavelength for p in actual]==[p.wavelength for p in s.peaks]
    np.testing.assert_array_equal(w.parallel_curves[index].yData,s.displayed)
    expected=s.displayed/s.displayed.max()
    np.testing.assert_allclose(w.curves[index].yData,expected)
    # Fixing invalidation must preserve the fast path for truly idle refreshes.
    with patch.object(w.curves[index], 'setData', wraps=w.curves[index].setData) as upload:
        for _ in range(5):w.refresh()
        upload.assert_not_called()
finally:
    w.close();app.processEvents()
""".replace('CHANGE',repr(change)), tmp_path)


@pytest.mark.parametrize('removal', ['absent', 'invisible'])
def test_identical_series_restores_peak_annotations(removal, tmp_path):
    run_ui("""
from types import SimpleNamespace
import numpy as np
from PySide6 import QtWidgets as W
from spectradesk.spectrum_plot import SpectrumPlot
app=W.QApplication([]);plot=SpectrumPlot(renderer='raster')
try:
    spec=dict(name='test',x=np.array([400.,550.,700.]),y=np.array([0.,100.,0.]),
        peaks=[SimpleNamespace(wavelength=550.)],unit='counts')
    plot._cursor_wave=550.
    plot.set_spectrum_series([dict(spec)])
    state=plot._series['test']
    assert state['peaks'].isVisible() and state['labels'][0].isVisible()
    plot.set_spectrum_series([] if REMOVAL=='absent' else [dict(spec,visible=False)])
    assert all(not item.isVisible() for item in [state['peaks'],state['cursor']]+state['labels'])
    plot.set_spectrum_series([dict(spec)])
    assert all(item.isVisible() for item in [state['peaks'],state['cursor']]+state['labels'])
    assert state['labels'][0].toPlainText()=='550.0'
    np.testing.assert_array_equal(state['peaks'].getData()[0],[550.])
finally:plot.close()
""".replace('REMOVAL',repr(removal)), tmp_path)
