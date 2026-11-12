"""Opt-in desktop OpenGL rendering check for the shared spectrum widget."""
import os,tempfile
from argparse import Namespace
from PySide6 import QtWidgets as W,QtTest
from spectradesk.workbench import Workbench
from spectradesk.spectrum_plot import SpectrumPlot
from spectradesk.gpu_curve import GpuSpectrumCurve
with tempfile.TemporaryDirectory() as directory:
    os.environ['XDG_CONFIG_HOME']=directory
    app=W.QApplication([]);window=Workbench(Namespace(demo=True,smoke=None,renderer='opengl'));window.show()
    try:
        for _ in range(250):
            if all(s.ready for s in window.sessions):break
            QtTest.QTest.qWait(20)
        assert all(s.ready for s in window.sessions)
        window.start_all()
        for _ in range(250):
            if all(s.frame_data is not None for s in window.sessions):break
            QtTest.QTest.qWait(20)
        assert all(s.frame_data is not None for s in window.sessions)
        window.stop_all();QtTest.QTest.qWait(200);window.timer.stop()
        for tab in range(4):
            window.tabs.setCurrentIndex(tab)
            for mode in range(4):
                for session in window.sessions:session.mode.setCurrentIndex(mode)
                window.refresh();QtTest.QTest.qWait(60);window.refresh()
                pairs=([(window.sessions[tab].plot,window.sessions[tab].curve)] if tab<2 else (list(zip(window.parallel_plots,window.parallel_curves)) if tab==3 else [(window.plot,c) for c in window.curves]))
                for plot,curve in pairs:
                    assert isinstance(plot,SpectrumPlot) and isinstance(curve,GpuSpectrumCurve)
                    image=plot.viewport().grabFramebuffer()
                    assert not image.isNull() and plot.viewport().context().isValid()
                    assert curve.glstate is not None and curve.last_error is None,(tab,mode,curve.last_error)
        window.tabs.setCurrentIndex(2);window.scale.setCurrentIndex(1);window.refresh()
        window.plot.viewport().grabFramebuffer();assert all(c.last_error is None for c in window.curves)
        print('All four views, four effects, dual axes: shared OpenGL rendering PASS')
    finally:window.close()
