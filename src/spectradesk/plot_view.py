"""Wavelength navigation shared by all spectrum views."""
import pyqtgraph as pg
from PySide6 import QtCore
class SpectrumViewBox(pg.ViewBox):
    def __init__(self):
        super().__init__(enableMenu=False);self.setMouseEnabled(x=False,y=False);self.manual_x=None;self.requested_x=None;self.navigation_target=None;self.y_scale_locked=False;self.y_scale_limits=(100.,100.)
    def bounded_range(self,low,high):
        bounds=self.requested_x
        maximum=(bounds[1]-bounds[0]) if bounds else 2000.
        minimum=min(5.,maximum)
        span=max(minimum,min(maximum,high-low));center=(low+high)/2
        low=center-span/2;high=center+span/2
        if bounds:
            if low<bounds[0]:low=bounds[0];high=low+span
            if high>bounds[1]:high=bounds[1];low=high-span
        return low,high
    def wheelEvent(self,event,axis=None):
        view=self.navigation_target or self
        if axis==1:
            if not view.y_scale_locked:
                event.accept();return
            low,high=view.viewRange()[1]
            steps=max(-2.,min(2.,event.delta()/120))
            span=high-low
            minimum,maximum=view.y_scale_limits
            requested=span*(.94**steps)
            # If fresh data changes the limit, approach it without a sudden jump.
            if span>maximum:new_span=max(maximum,min(span,requested))
            elif span<minimum:new_span=min(minimum,max(span,requested))
            else:new_span=max(minimum,min(maximum,requested))
            factor=new_span/span
            # Scale around zero so the zero baseline stays at the same screen position.
            view.setYRange(low*factor,high*factor,padding=0)
            event.accept();return
        low,high=view.viewRange()[0];center=view.mapSceneToView(event.scenePos()).x()
        steps=max(-2.,min(2.,event.delta()/120))
        factor=.94**steps
        view.manual_x=view.bounded_range(center+(low-center)*factor,center+(high-center)*factor)
        view.setXRange(*view.manual_x,padding=0);event.accept()
    def mouseDragEvent(self,event,axis=None):
        if event.button()!=QtCore.Qt.MouseButton.LeftButton:event.ignore();return
        view=self.navigation_target or self
        dx=view.mapSceneToView(event.lastScenePos()).x()-view.mapSceneToView(event.scenePos()).x()
        low,high=view.viewRange()[0];view.manual_x=view.bounded_range(low+dx,high+dx);view.setXRange(*view.manual_x,padding=0);event.accept()
    def mouseDoubleClickEvent(self,event):
        view=self.navigation_target or self;view.manual_x=None
        if view.requested_x:view.setXRange(*view.requested_x,padding=0)
        event.accept()
