"""Fixed spectral axes controlled by explicit wavelength inputs."""
import pyqtgraph as pg
class SpectrumViewBox(pg.ViewBox):
    def __init__(self):
        super().__init__(enableMenu=False)
        self.setMouseEnabled(x=False,y=False)
    def wheelEvent(self,event,axis=None):event.ignore()
    def mouseDragEvent(self,event,axis=None):event.ignore()
