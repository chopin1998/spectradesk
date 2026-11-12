"""A passive camera strip painted using the main spectrum's screen transform."""
import numpy as np
from shiboken6 import isValid
from PySide6 import QtCore,QtGui,QtWidgets as W

class CameraBand(W.QWidget):
    def __init__(self,window,parent=None):
        super().__init__(parent);self.window=window;self.image=None;self.qimage=None;self.bounds=QtCore.QRectF()
        self.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Expanding)
    def setImage(self,image,autoLevels=False):
        self.image=np.ascontiguousarray(image).copy();h,w=self.image.shape[:2]
        self.qimage=QtGui.QImage(self.image.data,w,h,self.image.strides[0],QtGui.QImage.Format.Format_RGB888).copy();self.update()
    def setRect(self,rect):self.bounds=rect;self.update()
    def screen_x(self,wavelength):
        plot=self.window.plot;view=self.window.spectrum_view
        position=plot.mapFromScene(view.mapViewToScene(QtCore.QPointF(wavelength,0)))
        return self.mapFromGlobal(plot.viewport().mapToGlobal(position)).x()
    def paintEvent(self,event):
        if self.qimage is None or getattr(self.window,'_closing',False) or not hasattr(self.window,'plot') or not isValid(self.window.plot):return
        painter=QtGui.QPainter(self)
        low,high=self.window.spectrum_view.viewRange()[0]
        left=self.screen_x(low);right=self.screen_x(high)
        painter.setClipRect(QtCore.QRectF(left,0,max(0,right-left),self.height()))
        painter.fillRect(self.rect(),QtGui.QColor('black'))
        start=self.screen_x(self.bounds.left());end=self.screen_x(self.bounds.right())
        painter.drawImage(QtCore.QRectF(start,0,end-start,self.height()),self.qimage)
        cursor=getattr(self.window,'cursor_wave',None)
        if cursor is not None:
            painter.setPen(QtGui.QPen(QtGui.QColor('white'),1));x=self.screen_x(cursor);painter.drawLine(x,0,x,self.height())
