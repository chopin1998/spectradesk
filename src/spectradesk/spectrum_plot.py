"""Shared spectrum widget, rendering backend and curve appearance."""
import pyqtgraph as pg
from PySide6 import QtGui,QtCore
from .gpu_curve import GpuSpectrumCurve
from .plot_view import SpectrumViewBox
import numpy as np
from shiboken6 import isValid

class SpectrumPlot(pg.PlotWidget):
    cursorMoved=QtCore.Signal(object)
    def __init__(self,*args,renderer='opengl',**kwargs):
        kwargs.setdefault('viewBox',SpectrumViewBox())
        super().__init__(*args,**kwargs);self.renderer=renderer
        self._series={};self._cursor_wave=None
        self.readout=pg.TextItem(anchor=(1,0),color='#9baaba',fill=pg.mkBrush(20,27,36,180));self.readout.setZValue(100);self.addItem(self.readout,ignoreBounds=True)
        self.scene().sigMouseMoved.connect(self.hover_spectrum)
        self.getViewBox().sigRangeChanged.connect(lambda *_:self.position_readout())
        self.useOpenGL(renderer=='opengl')
        self.setToolTip('滚轮缩放波长 · 左键拖动 · 双击恢复完整范围')
        self.getAxis('bottom').enableAutoSIPrefix(False)
    def set_display_range(self,low,high,force=False):
        view=self.getViewBox();requested=(float(low),float(high))
        if force or view.requested_x!=requested:view.manual_x=None;view.requested_x=requested
        if view.manual_x is None:self.setXRange(*requested,padding=0)
    def reset_navigation(self):
        view=self.getViewBox();view.manual_x=None
        if view.requested_x:self.setXRange(*view.requested_x,padding=0)
    def position_readout(self):
        if not isValid(self) or not isValid(self.readout):return
        xr,yr=self.getViewBox().viewRange();self.readout.setPos(xr[1],yr[1])
    def set_spectrum_series(self,series):
        names=set()
        for spec in series:
            name=spec['name'];names.add(name);view=spec.get('view',self.getViewBox())
            state=self._series.get(name)
            if state is None or state['view'] is not view:
                if state is not None:
                    for item in [state['cursor'],state['peaks']]+state['labels']:state['view'].removeItem(item)
                cursor=pg.ScatterPlotItem(size=10,brush='#ffe066',pen=pg.mkPen('#805615'));peaks=pg.ScatterPlotItem(size=6,brush=spec.get('color','#bd873c'),pen=None)
                for item in (cursor,peaks):item.setZValue(40);view.addItem(item,ignoreBounds=True)
                state=dict(view=view,cursor=cursor,peaks=peaks,labels=[]);self._series[name]=state
            state['spec']=spec;visible=spec.get('visible',True)
            x=np.asarray(spec['x']);y=np.asarray(spec['y']);positions=np.asarray([p.wavelength for p in spec.get('peaks',[])],dtype=float)
            heights=np.interp(positions,x,y) if x.size else np.array([])
            state['peaks'].setData(positions,heights);state['peaks'].setVisible(visible)
            while len(state['labels'])<min(8,len(positions)):
                text=pg.TextItem(anchor=(.5,1),color=spec.get('color','#bd873c'));text.setZValue(45);view.addItem(text,ignoreBounds=True);state['labels'].append(text)
            for i,label in enumerate(state['labels']):
                label.setVisible(visible and i<len(positions))
                if i<len(positions):label.setText(f'{positions[i]:.1f}');label.setPos(positions[i],heights[i])
        for name,state in self._series.items():
            if name not in names:
                state['spec']['visible']=False
                for item in [state['cursor'],state['peaks']]+state['labels']:item.hide()
        self.update_spectrum_cursor()
    def hover_spectrum(self,position):
        view=self.getViewBox()
        self._cursor_wave=view.mapSceneToView(position).x() if view.sceneBoundingRect().contains(position) else None
        self.update_spectrum_cursor();self.cursorMoved.emit(self._cursor_wave)
    def update_spectrum_cursor(self):
        parts=[];wave=self._cursor_wave
        for state in self._series.values():
            spec=state['spec'];x=np.asarray(spec['x']);y=np.asarray(spec['y'])
            if wave is None or not spec.get('visible',True) or not x.size or not x[0]<=wave<=x[-1]:state['cursor'].hide();continue
            value=float(np.interp(wave,x,y));state['cursor'].setData([wave],[value]);state['cursor'].show()
            parts.append(f"{spec['name']} {value:.2f} {spec['unit']}")
        self.readout.setText((f'{wave:.2f} nm · '+' · '.join(parts)) if parts else '')
        self.position_readout()

    def create_curve(self,**kwargs):
        curve=GpuSpectrumCurve(**kwargs) if self.renderer=='opengl' else pg.PlotDataItem(**kwargs)
        self.addItem(curve);return curve

def style_spectrum_curve(curve,mode,color):
    if isinstance(curve,GpuSpectrumCurve):curve.effect=mode
    key=(mode,color)
    if getattr(curve,'_shared_spectrum_style',None)==key:return
    curve._shared_spectrum_style=key;curve.setFillLevel(None)
    if mode in (1,2):
        gradient=QtGui.QLinearGradient(380,0,780,0)
        for value,stop in [(0,'#9068e9'),(.15,'#6588ff'),(.25,'#48d5ec'),(.375,'#78e59d'),(.5,'#e5e472'),(.625,'#f3aa67'),(.8,'#ed6e75'),(1,'#ae556b')]:gradient.setColorAt(value,QtGui.QColor(stop))
        pen=QtGui.QPen(QtGui.QBrush(gradient),1.8);pen.setCosmetic(True);curve.setPen(pen)
        if mode==2:
            for stop,fill in gradient.stops():fill.setAlpha(65);gradient.setColorAt(stop,fill)
            curve.setFillLevel(0);curve.setBrush(QtGui.QBrush(gradient))
    else:curve.setPen(pg.mkPen('#8affce' if mode==3 else color,width=1.8))
