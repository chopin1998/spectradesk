"""A small sampling-cycle indicator, animated entirely on the UI thread."""
import time
from PySide6 import QtCore,QtGui,QtWidgets as W


class SamplingIndicator(W.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFixedSize(22,22)
        self.period=None;self.started=None;self.active=False
        self.timer=QtCore.QTimer(self);self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.hide()

    def begin(self,started,reset=False):
        if reset:self.period=None
        self.started=started;self.active=True
        self.timer.start();self.tick()

    def tick(self):
        if not self.active:return
        elapsed=max(0.,time.monotonic()-self.started)
        # First/previously fast samples need no animation unless they exceed 200 ms.
        self.setVisible((self.period is not None and self.period>.2) or elapsed>=.2)
        self.update()

    def complete(self,period):
        self.period=max(float(period),1e-6);self.active=False;self.timer.stop()
        self.setVisible(self.period>.2)
        self.update()

    def stop(self):
        self.active=False;self.timer.stop();self.hide()

    def reset(self):
        self.stop();self.period=None;self.started=None

    def phase(self):
        if not self.active or self.started is None:return 0.
        # There is no timing estimate until the first frame has completed.
        return ((time.monotonic()-self.started)/(self.period or 1.))%1.

    def paintEvent(self,event):
        painter=QtGui.QPainter(self);painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        color=self.palette().color(QtGui.QPalette.ColorRole.Link)
        track=QtGui.QColor(color);track.setAlpha(55)
        rect=QtCore.QRectF(4,4,14,14)
        painter.setPen(QtGui.QPen(track,2.5));painter.drawEllipse(rect)
        painter.setPen(QtGui.QPen(color,2.5,QtCore.Qt.PenStyle.SolidLine,QtCore.Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect,int((90-self.phase()*360)*16),-110*16)
