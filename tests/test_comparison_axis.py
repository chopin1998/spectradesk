import numpy as np
from spectradesk.workbench import Workbench

class View:
    def __init__(self):self.limits=(0.,1.);self.updates=0
    def viewRange(self):return [(400.,700.),self.limits]
    def enableAutoRange(self,**kwargs):assert kwargs=={'axis':'y','enable':False}
    def setYRange(self,lo,hi,padding):self.limits=(lo,hi);self.updates+=1

class Curve:
    def __init__(self,peak):self.xData=np.array([450.,550.]);self.yData=np.array([0.,peak])
    def isVisible(self):return True

def test_headroom_noise_growth_and_delayed_shrink(monkeypatch):
    import spectradesk.workbench as module
    clock=[0.];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    view=View();curve=Curve(100.)
    fit=lambda:Workbench.fit_stable_y(None,view,[curve],5.,'camera')
    fit();assert view.limits==(-5.,120.)
    for peak in (101.,99.,104.,98.):curve.yData[-1]=peak;fit()
    assert view.updates==1
    curve.yData[-1]=125.;fit();assert view.limits[1]>=150.
    curve.yData[-1]=30.;fit();old=view.limits
    clock[0]=1.9;fit();assert view.limits==old
    clock[0]=2.1;fit();assert view.limits[1]==36.

def test_axis_ignores_outside_visible_wavelengths():
    view=View();curve=Curve(1.);curve.xData=np.array([200.,550.]);curve.yData=np.array([1000.,1.])
    Workbench.fit_stable_y(None,view,[curve],1.,'normalized')
    assert view.limits==(-.05,1.2)
