"""Display-only phosphor persistence texture; measurements are never modified."""
import time
import numpy as np
import pyqtgraph as pg
from scipy.ndimage import gaussian_filter

class PhosphorImage(pg.ImageItem):
    def __init__(self):
        super().__init__(axisOrder='row-major')
        self.history=np.zeros((192,512),dtype=np.float32)
        self.bounds=None;self.last_time=None
        lut=np.zeros((256,4),dtype=np.uint8)
        lut[:,0]=40;lut[:,1]=255;lut[:,2]=155;lut[:,3]=np.arange(256,dtype=np.uint8)
        self.setLookupTable(lut);self.setZValue(-5)
    def reset(self):
        self.history.fill(0);self.last_time=None;self.bounds=None;self.hide()
    def update_spectrum(self,x,y,bounds):
        now=time.monotonic()
        if self.bounds!=bounds:
            self.history.fill(0);self.bounds=bounds
        elif self.last_time is not None:self.history*=np.exp(-(now-self.last_time)/.55)
        self.last_time=now
        lo,hi,bottom,top=bounds
        h,w=self.history.shape
        samples=np.interp(np.linspace(lo,hi,w),x,y,left=np.nan,right=np.nan)
        valid=np.isfinite(samples)
        rows=np.clip(np.nan_to_num((samples-bottom)/(top-bottom)*(h-1),nan=0),0,h-1).astype(int)
        # Rasterize connected segments in one array operation.
        low=np.minimum(rows[:-1],rows[1:]);high=np.maximum(rows[:-1],rows[1:])
        trace=(np.arange(h)[:,None]>=low)&(np.arange(h)[:,None]<=high)&(valid[:-1]&valid[1:])
        self.history[:,:-1]=np.maximum(self.history[:,:-1],trace)
        glow=gaussian_filter(self.history,.9)
        image=np.minimum(1.,self.history*.55+glow*.8)
        self.setImage(image,levels=(0,1),autoLevels=False)
        self.setRect(pg.QtCore.QRectF(lo,bottom,hi-lo,top-bottom));self.show()
