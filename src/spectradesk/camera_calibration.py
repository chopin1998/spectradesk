"""Conservative peak suggestions; user reviews them before applying a fit."""
import numpy as np
from scipy.signal import find_peaks

def suggest_peak_pairs(pixels,gray,approximate_wave,reference_wave,reference_counts):
    px,g,cw,rx,ry=map(lambda v:np.asarray(v,dtype=float),(pixels,gray,approximate_wave,reference_wave,reference_counts))
    if px.ndim!=1 or px.shape!=g.shape or cw.shape!=g.shape or rx.ndim!=1 or rx.shape!=ry.shape or len(px)<4 or len(rx)<4:raise ValueError('光谱数据无效')
    if not all(np.isfinite(a).all() for a in (px,g,cw,rx,ry)) or np.any(np.diff(cw)<=0) or np.any(np.diff(rx)<=0):raise ValueError('光谱坐标须递增且数据有限')
    cp,_=find_peaks(g,prominence=max(1.,np.ptp(g)*.04),distance=5)
    rp,_=find_peaks(ry,prominence=max(1.,np.ptp(ry)*.04),distance=5)
    cp=cp[(cw[cp]>=380)&(cw[cp]<=700)];rp=rp[(rx[rp]>=380)&(rx[rp]<=700)]
    if len(cp)<4 or len(rp)<4:raise ValueError('可用谱峰不足4个，请检查曝光、光源或手工配对')
    distance=np.abs(cw[cp,None]-rx[rp][None,:]);pairs=[]
    for i,j in enumerate(np.argmin(distance,axis=1)):
        if distance[i,j]<=20 and np.argmin(distance[:,j])==i:pairs.append([px[cp[i]],rx[rp[j]]])
    pairs=np.asarray(pairs)
    while len(pairs)>=4:
        coeff=np.polyfit(pairs[:,0],pairs[:,1],2);res=np.polyval(coeff,pairs[:,0])-pairs[:,1]
        if np.max(np.abs(res))<=2.5:break
        pairs=np.delete(pairs,np.argmax(np.abs(res)),axis=0)
    if len(pairs)<4 or np.ptp(pairs[:,1])<100:raise ValueError('自动配对不够可靠，请手工确认对应峰；原标定不能偏离太大')
    return pairs,res
