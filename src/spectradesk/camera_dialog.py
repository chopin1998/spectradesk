from dataclasses import asdict
from pathlib import Path
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets as W
import pyqtgraph as pg
from .camera import CameraProfile,cameras
from .camera_calibration import suggest_peak_pairs

class CameraDialog(W.QDialog):
    """Configure while disconnected; inspect the last captured image without owning camera."""
    def __init__(self,profile,path,frame=None,parent=None,reference_frame=None):
        super().__init__(parent);self.setWindowTitle('摄像头设置与波长校准');self.resize(1100,900)
        self.profile=CameraProfile(**asdict(profile));self.frame=frame;self.reference_frame=reference_frame
        layout=W.QVBoxLayout(self);geometry=W.QWidget();form=W.QFormLayout(geometry)
        advanced=W.QPushButton('图像几何 / 相机设备（高级）');advanced.setCheckable(True);advanced.toggled.connect(geometry.setVisible);layout.addWidget(advanced);layout.addWidget(geometry);geometry.hide()
        self.device=W.QComboBox();self.device.setEditable(True);self.device.addItems(cameras());self.device.setCurrentText(path);form.addRow('相机设备',self.device)
        self.fields={}
        for key,title,lo,hi in [('width','宽度 / px',16,8192),('height','高度 / px',16,8192),('start_x','横向起点 / 千分比',0,999),('end_x','横向终点 / 千分比',1,1000),('start_y','距顶边 / %',0,99),('size_y','条带高度 / %',1,100)]:
            box=W.QSpinBox();box.setRange(lo,hi);box.setValue(getattr(profile,key));self.fields[key]=box;form.addRow(title,box)
        self.flip=W.QCheckBox('水平翻转');self.flip.setChecked(profile.flip);form.addRow(self.flip)
        self.preview=W.QLabel('先采集一帧，可预览图像和选择校准峰；窗口使用打开时的快照。');self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.preview)
        self.plot=pg.PlotWidget();self.plot.setMinimumHeight(160);self.plot.setLabel('bottom','翻转后的全图像素');self.curve=self.plot.plot();layout.addWidget(self.plot)
        self.plot.scene().sigMouseClicked.connect(self.pick)
        self.calibration_mode=W.QComboBox();self.calibration_mode.addItems(['手工标定（输入已知波长）','FLA5000 参考标定（三原色灯）']);layout.addWidget(self.calibration_mode)
        self.reference_plot=pg.PlotWidget();self.reference_plot.setMinimumHeight(160);self.reference_plot.setLabel('bottom','FLA5000 参考波长',units='nm');self.reference_plot.getAxis('bottom').enableAutoSIPrefix(False)
        self.reference_curve=self.reference_plot.plot(pen=pg.mkPen('#459be8'));layout.addWidget(self.reference_plot)
        self.reference_plot.scene().sigMouseClicked.connect(self.pick_reference)
        self.calibration_mode.currentIndexChanged.connect(lambda index:self.reference_plot.setVisible(index==1))
        self.reference_plot.hide()
        if reference_frame is not None:self.set_reference(reference_frame)
        self.table=W.QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['全图像素（可点击曲线填写）','参考波长 / nm']);self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch);self.table.setMinimumHeight(100);self.table.setMaximumHeight(150);layout.addWidget(self.table)
        if reference_frame is None:
            for p,w in profile.points:self.add_point(p,w)
        row=W.QHBoxLayout();layout.addLayout(row)
        for title,fn in [('添加参考点',lambda:self.add_point()),('删除所选点',self.remove_point),('清空参考点',lambda:self.table.setRowCount(0)),('导入 Theremino 3.1 INI',self.import_ini),('加载 FLA5000 参考 NPZ',self.reference)]:
            b=W.QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.degree=W.QComboBox();self.degree.addItems(['线性拟合','二次拟合','单点偏移（保留色散）']);self.degree.setCurrentIndex(1 if len(profile.coefficients)==3 else 0);row.addWidget(self.degree)
        self.auto_pair_button=W.QPushButton('三原色灯：自动找峰配对（生成草案）');self.auto_pair_button.clicked.connect(self.auto_pair);layout.addWidget(self.auto_pair_button)
        self.message=W.QLabel('手工：点击相机峰填像素，再输入已知波长。FLA5000：先点击相机峰，再点击同一谱峰的参考曲线。线性至少2点，二次至少3点；请留出额外谱峰验证。钠双线若不能分辨，请勿当作两个独立点。');self.message.setWordWrap(True);layout.addWidget(self.message)
        buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save|W.QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.original_geometry=self.geometry_key(profile)
        for box in self.fields.values():box.valueChanged.connect(self.update_preview)
        self.flip.toggled.connect(self.update_preview);self.update_preview()
    @staticmethod
    def geometry_key(p):return (p.width,p.height,p.start_x,p.end_x,p.start_y,p.size_y,p.flip)
    def read_fields(self):
        for key,box in self.fields.items():setattr(self.profile,key,box.value())
        self.profile.flip=self.flip.isChecked();return self.profile
    def add_point(self,p='',w=''):
        row=self.table.rowCount();self.table.insertRow(row)
        for col,value in enumerate((p,w)):self.table.setItem(row,col,W.QTableWidgetItem(str(value)))
        self.table.setCurrentCell(row,0)
    def remove_point(self):
        if self.table.currentRow()>=0:self.table.removeRow(self.table.currentRow())
    def pick(self,event):
        if not self.plot.sceneBoundingRect().contains(event.scenePos()):return
        pixel=self.plot.plotItem.vb.mapSceneToView(event.scenePos()).x()
        if self.curve.xData is not None:
            mask=np.flatnonzero(np.abs(self.curve.xData-pixel)<=8)
            if mask.size:pixel=self.curve.xData[mask[np.argmax(self.curve.yData[mask])]]
        row=self.table.currentRow()
        if row<0:self.add_point();row=self.table.currentRow()
        self.table.item(row,0).setText(f'{pixel:.3f}')
    def update_preview(self,*_):
        if self.frame is None or 'camera_image' not in self.frame:return
        try:
            p=self.read_fields();image=self.frame['camera_image'];y,_=p.extract(image);x,top,width,height=p.roi();self.curve.setData(np.arange(x,x+width),y)
            rgb=np.ascontiguousarray((image[:,::-1] if p.flip else image)[:,:,::-1]);q=QtGui.QImage(rgb.data,p.width,p.height,rgb.strides[0],QtGui.QImage.Format.Format_RGB888).copy()
            painter=QtGui.QPainter(q);painter.setPen(QtGui.QPen(QtGui.QColor('red'),3));painter.drawRect(x,top,width,height);painter.end();self.preview.setPixmap(QtGui.QPixmap.fromImage(q).scaled(760,140,QtCore.Qt.AspectRatioMode.KeepAspectRatio))
        except ValueError as e:self.message.setText(str(e))
    def import_ini(self):
        path,_=W.QFileDialog.getOpenFileName(self,'选择 v3.1 配置','','INI 文本 (*.txt *.ini)')
        if not path:return
        try:
            self.profile=CameraProfile.from_ini(path);self.table.setRowCount(0)
            for key,box in self.fields.items():
                with QtCore.QSignalBlocker(box):box.setValue(getattr(self.profile,key))
            self.flip.setChecked(self.profile.flip);self.original_geometry=self.geometry_key(self.profile);self.update_preview();self.message.setText('已导入卖家参数；保存后重新连接生效。')
        except Exception as e:W.QMessageBox.warning(self,'导入失败',str(e))
    def set_reference(self,frame):
        x=np.asarray(frame['wave']);y=np.asarray(frame['corrected'])
        if x.ndim!=1 or y.shape!=x.shape or not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.diff(x)<=0):raise ValueError('参考数据无效')
        self.reference_frame=dict(frame,wave=x.copy(),corrected=y.copy())
        self.reference_curve.setData(x,y);self.calibration_mode.setCurrentIndex(1)
    def pick_reference(self,event):
        if self.reference_frame is None or not self.reference_plot.sceneBoundingRect().contains(event.scenePos()):return
        wave=self.reference_plot.plotItem.vb.mapSceneToView(event.scenePos()).x()
        x=self.reference_frame['wave'];y=self.reference_frame['corrected'];ids=np.flatnonzero(np.abs(x-wave)<=3)
        if ids.size:wave=x[ids[np.argmax(y[ids])]]
        row=self.table.currentRow()
        if row<0:self.add_point();row=self.table.currentRow()
        self.table.item(row,1).setText(f'{wave:.5f}')
    def reference(self):
        path,_=W.QFileDialog.getOpenFileName(self,'加载 FLA5000 测量','','SpectraDesk (*.npz)')
        if not path:return
        try:
            import json
            with np.load(path,allow_pickle=False) as data:
                meta=json.loads(str(data['metadata']))
                if meta.get('backend')=='camera' or meta.get('device',{}).get('model')!='FLA5000':raise ValueError('请选择 FLA5000 的完整测量文件')
                self.set_reference(dict(wave=data['wavelength_nm'],corrected=data['corrected_counts'],utc=meta.get('utc',''),device=meta.get('device',{})))
        except Exception as e:W.QMessageBox.warning(self,'参考读取失败',str(e))
    def auto_pair(self):
        try:
            if self.frame is None or self.reference_frame is None:raise ValueError('请先用两台采集同一光源，或加载 FLA5000 参考文件')
            if self.frame.get('saturated'):raise ValueError('相机图像饱和，请降低曝光后重新采集')
            p=self.read_fields();wave,_=p.wavelengths();gray,saturated=p.extract(self.frame['camera_image'])
            if saturated:raise ValueError('相机原图颜色通道饱和，不能自动标定')
            start,_,width,_=p.roi()
            points,residual=suggest_peak_pairs(np.arange(start,start+width),gray,wave,self.reference_frame['wave'],self.reference_frame['corrected'])
            candidate=CameraProfile(**asdict(p));candidate.fit(points,2)
            self.table.setRowCount(0)
            for pixel,wavelength in points:self.add_point(f'{pixel:.2f}',f'{wavelength:.5f}')
            self.degree.setCurrentIndex(1);self.calibration_mode.setCurrentIndex(1)
            self.message.setText(f'已建议 {len(points)} 对峰；二次拟合最大残差 {np.max(np.abs(residual)):.2f} nm。请检查配对，可删除或修改错误行，确认后点保存。残差不等于绝对精度。')
        except Exception as error:W.QMessageBox.warning(self,'自动配对',str(error))
    def save(self):
        try:
            p=self.read_fields();points=[]
            for row in range(self.table.rowCount()):points.append([float(self.table.item(row,col).text()) for col in (0,1)])
            if self.geometry_key(p)!=self.original_geometry and not points:raise ValueError('图像几何已改变，请添加参考点重新校准，或重新导入匹配配置')
            if p.device and p.device!=self.device.currentText() and not points:raise ValueError('相机已改变，请重新校准或导入配置')
            if points:
                if self.calibration_mode.currentIndex()==1 and self.reference_frame is None:raise ValueError('请先采集或加载 FLA5000 参考光谱')
                if self.frame is not None and self.frame.get('saturated'):raise ValueError('相机图像饱和，请降低曝光并重新采集后标定')
                residual=p.fit(points,(1,2,0)[self.degree.currentIndex()])
                p.source=('FLA5000 对照标定 · '+str(self.reference_frame.get('utc','')) if self.calibration_mode.currentIndex()==1 else '用户手工谱线标定')
                detail='\n'.join(f'{point[1]:.3f} nm：{err:+.4f} nm' for point,err in zip(sorted(points),residual))
                W.QMessageBox.information(self,'拟合残差',detail+'\n仅为拟合残差，请用未参与拟合的谱线验证。')
            p.device=self.device.currentText().strip()
            if not p.device:raise ValueError('请选择或填写相机设备路径')
            p.validate();self.accept()
        except Exception as e:W.QMessageBox.warning(self,'无法保存',str(e))
