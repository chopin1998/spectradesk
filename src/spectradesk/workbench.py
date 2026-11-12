"""Two independent acquisition sessions with an optional shared comparison view."""
from argparse import Namespace
from types import SimpleNamespace
from pathlib import Path
import os,tempfile,time
from .storage import save_measurement
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets as W
import pyqtgraph as pg
from .app import Window
from .spectrum_plot import SpectrumPlot,style_spectrum_curve
from .plot_view import SpectrumViewBox
from .camera_dialog import CameraDialog
from .camera import CameraProfile,display_camera_profile


class Workbench(W.QMainWindow):
    def __init__(self,args):
        super().__init__();self._closing=False;self.peak_offset=0.;self._syncing_parallel=False;self.renderer=getattr(args,'renderer','opengl')
        self._last_sampling_state=();self._pending_starts=set();self._tab_state_key=None;self._tab_icons={}
        self._navigation_timer=QtCore.QTimer(self);self._navigation_timer.setSingleShot(True);self._navigation_timer.setInterval(100);self._navigation_timer.timeout.connect(self.navigate_sampling_tab)
        self.setWindowTitle('SpectraDesk · 双设备光谱工作台')
        self.resize(1560,1040)
        root=W.QWidget();layout=W.QHBoxLayout(root);layout.setContentsMargins(12,10,12,10);self.setCentralWidget(root)
        self.sidepanel=W.QScrollArea();self.sidepanel.setWidgetResizable(True)
        self.sidepanel.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidepanel.setFixedWidth(400);layout.addWidget(self.sidepanel)
        side_root=W.QWidget();self.side=W.QVBoxLayout(side_root);self.side.setContentsMargins(4,4,4,4);self.side.setSpacing(24)
        self.sidepanel.setWidget(side_root)
        self.no_devices=W.QLabel('未检测到光谱仪\n请连接设备');self.no_devices.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);self.no_devices.setWordWrap(True);self.no_devices.setMinimumHeight(180);self.side.addWidget(self.no_devices,1)
        self.device_cards=[];self.device_control_layouts=[];self.device_controls=[];self.device_panels=[]
        for index,title in enumerate(('FLIGHT FLA5000','Camera / Theremino')):
            card=W.QFrame();card.hide();card.setObjectName(f'devicePanel{index}');self.device_panels.append(card);box=W.QVBoxLayout(card);box.setContentsMargins(12,10,12,10);box.setSpacing(7)
            heading=W.QHBoxLayout();name=W.QLabel(title);name.setObjectName('deviceHeading');name.setWordWrap(True);heading.addWidget(name,1);box.addLayout(heading)
            status=W.QLabel('正在查找设备…');status.setWordWrap(True);box.addWidget(status)
            connect=W.QPushButton('连接设备');connect.clicked.connect(lambda _,i=index:self.sessions[i].toggle_connection());heading.addWidget(connect)
            if index==1:
                config=W.QPushButton('相机预览与波长校准…');config.clicked.connect(lambda:self.sessions[1].configure_camera());config.hide()
                dark=W.QPushButton('记录当前暗背景');dark.clicked.connect(lambda:self.sessions[1].capture_camera_dark());dark.hide()
            else:config=dark=None
            self.device_control_layouts.append(box)
            self.side.addWidget(card);self.device_cards.append((status,connect,config,dark))
        self.tabs=W.QTabWidget();self.content=W.QStackedWidget();self.content.addWidget(self.tabs);self.content.addWidget(W.QWidget());layout.addWidget(self.content,1)
        actions=W.QWidget();actions_layout=W.QHBoxLayout(actions);actions_layout.setContentsMargins(0,0,0,0)
        calibration=W.QPushButton('设备校准');calibration.clicked.connect(self.calibration_dialog);actions_layout.addWidget(calibration)
        self.save_all_button=W.QPushButton('保存测量…');self.save_all_button.clicked.connect(self.save_measurements);actions_layout.addWidget(self.save_all_button)
        self.align_button=W.QPushButton('峰对齐…');self.align_button.clicked.connect(self.peak_alignment_dialog);actions_layout.insertWidget(0,self.align_button)
        self.tabs.setCornerWidget(actions,QtCore.Qt.Corner.TopRightCorner)
        self.parallel=W.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.parallel_plots=[];self.parallel_curves=[]
        for title,color in [('FLA5000 · counts','#459be8'),('摄像头 · DN','#e29a32')]:
            panel=W.QWidget();column=W.QVBoxLayout(panel);column.setContentsMargins(4,4,4,4)
            column.addWidget(W.QLabel(title))
            plot=SpectrumPlot(renderer=self.renderer);plot.getAxis('left').setWidth(max(72,self.fontMetrics().horizontalAdvance('-100000')+16));plot.setLabel('bottom','波长',units='nm');plot.getAxis('bottom').enableAutoSIPrefix(False)
            plot.showGrid(x=True,y=True,alpha=.2);curve=plot.create_curve(pen=pg.mkPen(color,width=2))
            column.addWidget(plot,1);self.parallel.addWidget(panel)
            self.parallel_plots.append(plot);self.parallel_curves.append(curve)
        for index,plot in enumerate(self.parallel_plots):
            plot.getViewBox().sigXRangeChanged.connect(lambda _,ranges,i=index:self.sync_parallel_x(i))
        self.sessions=[]
        for backend,title in [('fla5000','FLA5000'),('camera','摄像头光谱仪')]:
            options=Namespace(**vars(args));options.backend=backend;options.smoke=None
            session=Window(options);session.setParent(self.tabs);session.setWindowFlags(QtCore.Qt.WindowType.Widget)
            self.sessions.append(session);self.tabs.addTab(session,title)
            session.worker.state.connect(self.device_state_changed,QtCore.Qt.ConnectionType.QueuedConnection)
            body=session.centralWidget().layout().itemAt(1).layout()
            scroll=body.itemAt(0).widget();body.removeWidget(scroll)
            controls=scroll.takeWidget();controls.setMinimumWidth(0);controls.setMaximumWidth(16777215)
            original_device=controls.layout().itemAt(0).widget();original_device.hide()
            controls.setParent(session);controls.hide()
            session._original_controls=controls
            compact=self.compact_controls(session)
            self.device_control_layouts[len(self.sessions)-1].addWidget(compact)
            self.device_controls.append(compact);scroll.deleteLater()
            session.status.removeWidget(session.measure_status);session.status.removeWidget(session.sampling_indicator)
            progress=W.QHBoxLayout();progress.setContentsMargins(0,0,0,0)
            session.measure_status.setWordWrap(True);session.measure_status.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Preferred)
            progress.addWidget(session.sampling_indicator);progress.addWidget(session.measure_status,1)
            self.device_control_layouts[len(self.sessions)-1].insertLayout(2,progress);session.measure_status.show()
            session.info_button.setText('设备校准');session.info_button.clicked.disconnect();session.info_button.clicked.connect(self.calibration_dialog)
            session.save_button.clicked.disconnect();session.save_button.clicked.connect(self.save_measurements)
            session.info_button.hide();session.save_button.hide()
        self.compare=W.QWidget();comparison=W.QVBoxLayout(self.compare)
        row=W.QHBoxLayout();comparison.addLayout(row)
        self.scale=W.QComboBox();self.scale.addItems(['各自峰值归一化','原始单位 · 左 counts / 右 DN']);row.addWidget(self.scale)
        self.visible=[]
        for title in ('FLA5000','摄像头'):
            check=W.QCheckBox(title);check.setChecked(True);row.addWidget(check);self.visible.append(check)
        reset=W.QPushButton('完整波段');reset.clicked.connect(self.reset_comparison);row.addWidget(reset);row.addStretch()
        self.align_bottom=W.QCheckBox('底部对齐');self.align_bottom.toggled.connect(self.bottom_alignment_changed);row.addWidget(self.align_bottom)
        self.plot=SpectrumPlot(renderer=self.renderer);comparison.addWidget(self.plot,1)
        self.plot.setLabel('bottom','波长',units='nm');self.plot.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot.showGrid(x=True,y=True,alpha=.2)
        self.legend=self.plot.addLegend()
        self.curves=[self.plot.create_curve(pen=pg.mkPen(color,width=2)) for color in ('#459be8','#e29a32')]
        self.right=SpectrumViewBox();self.right.navigation_target=self.plot.getViewBox();self.plot.scene().addItem(self.right);self.right.setXLink(self.plot.getViewBox())
        self.plot.getAxis('right').linkToView(self.right)
        for curve,name in zip(self.curves,('FLA5000','摄像头')):self.legend.addItem(curve,name)
        self.plot.getViewBox().sigResized.connect(self.resize_right)
        self.tabs.addTab(self.compare,'叠加')
        self.tabs.addTab(self.parallel,'上下显示')
        self.side.addStretch()
        self.dual_axis=False
        self.scale.currentIndexChanged.connect(self.change_scale)
        for check in self.visible:check.toggled.connect(self.refresh)
        for session in self.sessions:session.theme.currentIndexChanged.connect(self.sync_theme)
        self.sync_theme(self.sessions[0].theme.currentIndex())
        W.QApplication.instance().styleHints().colorSchemeChanged.connect(lambda *_:self.update_device_styles())
        self.timer=QtCore.QTimer(self);self.timer.setInterval(120);self.timer.timeout.connect(self.refresh);self.timer.start()
        self.tabs.currentChanged.connect(self.select_view)
        self.change_scale();self.select_view(0)
        store=QtCore.QSettings('SpectraDesk','SpectraDesk');geometry=store.value('workbench/geometry')
        if isinstance(geometry,QtCore.QByteArray):self.restoreGeometry(geometry)
        sizes=store.value('workbench/vertical-splitter')
        if isinstance(sizes,list) and len(sizes)==2:self.parallel.setSizes([int(v) for v in sizes])

    def sync_parallel_x(self,index):
        if self._syncing_parallel:return
        self._syncing_parallel=True
        try:
            source=self.parallel_plots[index].getViewBox();target=self.parallel_plots[1-index].getViewBox()
            target.manual_x=source.manual_x;target.requested_x=source.requested_x
            target.setXRange(*source.viewRange()[0],padding=0)
        finally:self._syncing_parallel=False

    def set_peak_offset(self,offset):
        self.peak_offset=float(offset)
        self.align_button.setText(f'峰对齐 {offset:+.2f} nm' if offset else '峰对齐…')
        self.refresh()

    def peak_alignment_dialog(self):
        if not all(s.frame_data is not None and s.peaks for s in self.sessions):
            W.QMessageBox.information(self,'峰对齐','请先用两台采集光谱，并确认各自有可识别的峰。');return
        peaks=[list(s.peaks) for s in self.sessions]
        dialog=W.QDialog(self);dialog.setWindowTitle('峰对齐 · 对比显示平移');layout=W.QFormLayout(dialog)
        boxes=[]
        for title,points in zip(('FLA5000 参考峰','摄像头对应峰'),peaks):
            box=W.QComboBox()
            for point in points:box.addItem(f'{point.wavelength:.3f} nm',point.wavelength)
            layout.addRow(title,box);boxes.append(box)
        nearest=min(range(len(peaks[1])),key=lambda i:abs(peaks[1][i].wavelength-peaks[0][0].wavelength));boxes[1].setCurrentIndex(nearest)
        description=W.QLabel('选择同一个谱峰。仅平移摄像头对比曲线，不修改校准和保存数据。');description.setWordWrap(True);layout.addRow(description)
        offset=W.QLabel();layout.addRow('摄像头显示偏移',offset)
        def update(*_):offset.setText(f'{boxes[0].currentData()-boxes[1].currentData():+.3f} nm')
        for box in boxes:box.currentIndexChanged.connect(update)
        update()
        buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply|W.QDialogButtonBox.StandardButton.Reset|W.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(lambda:(self.set_peak_offset(boxes[0].currentData()-boxes[1].currentData()),dialog.accept()))
        buttons.button(W.QDialogButtonBox.StandardButton.Reset).clicked.connect(lambda:(self.set_peak_offset(0),dialog.accept()))
        buttons.rejected.connect(dialog.reject);layout.addRow(buttons);dialog.exec()

    @QtCore.Slot(str)
    def device_state_changed(self,text):
        if self._closing:return
        source=self.sender()
        for index,session in enumerate(self.sessions):
            if session.worker is source:
                self.device_tab_event(index,text)
                return

    def device_tab_event(self,index,text):
        if self._closing:return
        if text in ('连续采集中','单次采集中') or text=='自动积分 · 正在寻找合适强度':
            self._pending_starts.add(index)
            if not self._navigation_timer.isActive():self._navigation_timer.start()
        self.update_tab_states()

    def navigate_sampling_tab(self):
        if self._closing:return
        active=[i for i,s in enumerate(self.sessions) if s.ready and s.busy]
        starts=self._pending_starts;self._pending_starts=set()
        target=active[0] if len(active)==1 else (next(iter(starts)) if not active and len(starts)==1 else None)
        if target is not None:self.tabs.setCurrentIndex(target)

    def update_tab_states(self):
        if self._closing:return
        if not hasattr(self,'sessions') or self.tabs.count()<4:return
        active=tuple(i for i,s in enumerate(self.sessions) if s.ready and s.busy)
        if active!=self._last_sampling_state:
            self._last_sampling_state=active
            if len(active)==1 and not self._navigation_timer.isActive():self._navigation_timer.start()
        mode=self.sessions[0].theme.currentText()
        dark=mode=='暗色' or (mode=='跟随系统' and W.QApplication.instance().styleHints().colorScheme()==QtCore.Qt.ColorScheme.Dark)
        colors=('#77d6a4','#88bff4','#e9c088','#96a1ad','#f08e83') if dark else ('#26724b','#285c8c','#9c6517','#74808b','#b03a32')
        states=[]
        for session in self.sessions:
            if session.connecting:state=('连接中',2)
            elif session.ready:state=('采集中',0) if session.busy else ('可用',1)
            elif '异常' in session.device_status.text():state=('异常',4)
            elif session.device_present:state=('待连接',2)
            else:state=('未找到设备',3)
            states.append(state)
        comparison=('双设备采集中',0) if len(active)==2 else (('单设备采集中',2) if active else (('可对比',1) if all(s.frame_data is not None for s in self.sessions) else ('等待测量数据',3)))
        states.extend([comparison,comparison]);key=(dark,tuple(states))
        if self._tab_state_key==key:return
        self._tab_state_key=key;bar=self.tabs.tabBar()
        for index,(label,color_index) in enumerate(states):
            color=colors[color_index]
            if color not in self._tab_icons:
                pixmap=QtGui.QPixmap(12,12);pixmap.fill(QtCore.Qt.GlobalColor.transparent)
                painter=QtGui.QPainter(pixmap);painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing);painter.setPen(QtCore.Qt.PenStyle.NoPen);painter.setBrush(QtGui.QColor(color));painter.drawEllipse(1,1,10,10);painter.end();self._tab_icons[color]=QtGui.QIcon(pixmap)
            bar.setTabTextColor(index,QtGui.QColor(color));bar.setTabIcon(index,self._tab_icons[color])
            self.tabs.widget(index).setAccessibleDescription(self.tabs.tabText(index)+'：'+label)

    def compact_controls(self,session):
        session.compact_sidebar=True
        session.integration_label.setText('曝光时间' if session.args.backend=='camera' else '积分时间')
        panel=W.QWidget();grid=W.QGridLayout(panel);grid.setContentsMargins(0,2,0,0);grid.setHorizontalSpacing(12);grid.setVerticalSpacing(6);grid.setColumnMinimumWidth(0,126);grid.setColumnStretch(1,1)
        grid.addWidget(session.integration_label,0,0);grid.addWidget(session.integration,0,1);grid.addWidget(session.camera_exposure,0,1)
        grid.addWidget(session.camera_exposure_auto,1,0,1,2);grid.addWidget(session.auto_button,1,1)
        grid.addWidget(session.camera_exposure_status,2,0,1,2)
        grid.addWidget(W.QLabel('平均帧数'),3,0);grid.addWidget(session.average,3,1)
        row=W.QHBoxLayout();row.setSpacing(8);row.addWidget(session.single);row.addWidget(session.run);grid.addLayout(row,4,0,1,2)
        grid.addWidget(W.QLabel('显示'),5,0);grid.addWidget(session.mode,5,1)
        grid.addWidget(W.QLabel('平滑'),6,0);grid.addWidget(session.smooth,6,1)
        grid.addWidget(session.overlay,7,0,1,2)
        grid.addWidget(W.QLabel('波长 / nm'),8,0)
        row=W.QHBoxLayout();row.setSpacing(8);row.addWidget(session.display_start);row.addWidget(session.display_end);grid.addLayout(row,8,1)
        session.reset_view.setText('完整波段');grid.addWidget(session.reset_view,9,0,1,2)
        panel.setStyleSheet('QPushButton {padding:3px 6px;} QSpinBox,QDoubleSpinBox,QComboBox {padding:3px;}')
        return panel

    def calibration_dialog(self):
        dialog=W.QDialog(self);dialog.setWindowTitle('设备校准');dialog.resize(620,540)
        layout=W.QVBoxLayout(dialog);tabs=W.QTabWidget();layout.addWidget(tabs)
        borrowed=[]
        for index,session in enumerate(self.sessions):
            page=W.QWidget();column=W.QVBoxLayout(page)
            column.addWidget(W.QLabel(('FLA5000','摄像头光谱仪')[index]))
            info=W.QPushButton('查看设备与校准档案');info.setEnabled(session.ready);info.clicked.connect(session.show_info);column.addWidget(info)
            if index==1:
                button=W.QPushButton('使用 FLA5000 当前光谱标定（三原色灯）');button.clicked.connect(lambda:self.calibrate_camera(True));column.addWidget(button)
                manual=W.QPushButton('手工标定（钠灯等已知谱线）');manual.clicked.connect(lambda:self.calibrate_camera(False));column.addWidget(manual)
                compare=W.QPushButton('查看校准前 / 校准后 / FLA5000 对照');compare.setEnabled(session.frame_data is not None);compare.clicked.connect(self.show_calibration_comparison);column.addWidget(compare)
                dark=W.QPushButton(session.camera_dark.text());dark.setEnabled(session.ready and session.frame_data is not None);dark.clicked.connect(session.capture_camera_dark);column.addWidget(dark)
            calibration=session._original_controls.layout().itemAt(3).widget()
            column.addWidget(calibration);calibration.show();borrowed.append((calibration,session._original_controls))
            column.addStretch();tabs.addTab(page,('FLA5000','摄像头光谱仪')[index])
        close=W.QPushButton('关闭');close.clicked.connect(dialog.accept);layout.addWidget(close)
        try:dialog.exec()
        finally:
            for widget,parent in borrowed:parent.layout().insertWidget(3,widget);widget.hide()
            dialog.deleteLater()

    def show_calibration_comparison(self):
        camera=self.sessions[1]
        if camera.frame_data is None:return
        camera.render();frame=camera.frame_data
        profile=CameraProfile(**frame['device'].get('camera_profile',{}))
        before=display_camera_profile(profile,False).wavelengths()[0]
        dialog=W.QDialog(self);dialog.setWindowTitle('波长校准前后对照（当前测量快照）');dialog.resize(1000,600)
        layout=W.QVBoxLayout(dialog);plot=pg.PlotWidget();plot.addLegend();plot.setLabel('bottom','波长 (nm)');plot.setLabel('left','各自峰值归一化');layout.addWidget(plot)
        values=camera.corrected.copy();values=values/max(float(np.max(values)),1e-9)
        plot.plot(before,values,pen=pg.mkPen('#9eabb9',width=1.5,style=QtCore.Qt.PenStyle.DashLine),name='校准前 · 卖家映射')
        plot.plot(frame['wave'],values,pen=pg.mkPen('#e29a32',width=2),name='当前校准选择')
        fla=self.sessions[0]
        if fla.frame_data is not None:
            y=fla.corrected_data()[0];plot.plot(fla.frame_data['wave'],y/max(float(np.max(y)),1e-9),pen=pg.mkPen('#459be8',width=2),name='FLA5000 参考')
        plot.setXRange(380,700,padding=0);plot.showGrid(x=True,y=True,alpha=.2)
        close=W.QPushButton('关闭');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()

    def calibrate_camera(self,use_reference=False):
        camera=self.sessions[1];reference=None
        if use_reference:
            fla=self.sessions[0]
            if fla.frame_data is None or camera.frame_data is None:
                W.QMessageBox.information(self,'参考标定','请先用两台设备采集同一光源，再打开参考标定。');return
            f=fla.frame_data
            if f.get('demo')!=camera.frame_data.get('demo'):
                W.QMessageBox.warning(self,'参考标定','参考与相机数据必须同为实测数据。');return
            if np.any(32767-f['adc_frames'].astype(np.int32)>=16500):
                W.QMessageBox.warning(self,'参考标定','FLA5000 参考帧已饱和，请降低积分后重新采集。');return
            reference=dict(wave=f['wave'].copy(),corrected=fla.corrected_data()[0].copy(),utc=f['utc'],device=f['device'])
        dialog=CameraDialog(camera.camera_profile,camera.camera_path,camera.frame_data,self,reference_frame=reference)
        if camera.ready:
            for box in dialog.fields.values():box.setEnabled(False)
            dialog.device.setEnabled(False);dialog.flip.setEnabled(False)
        if dialog.exec()!=W.QDialog.DialogCode.Accepted:return
        try:
            was_connected=camera.ready
            dialog.profile.save(camera.camera_profile_path)
            camera.camera_profile=dialog.profile;camera.camera_path=dialog.profile.device
            camera.select_backend(1)
            if was_connected:camera.connect_request.emit()
        except Exception as error:W.QMessageBox.warning(self,'标定保存失败',str(error))

    def save_snapshots(self):
        connected=[s for s in self.sessions if s.ready]
        targets=connected if connected else [s for s in self.sessions if s.frame_data is not None]
        if not targets:raise ValueError('请先采集测量数据')
        if any(s.frame_data is None for s in targets):raise ValueError('已连接设备中有设备尚未采集，请先采集后再保存')
        snapshots=[]
        for session in targets:
            session.render()
            snapshots.append((session.args.backend,dict(session.frame_data),session.corrected.copy(),session.displayed.copy(),list(session.peaks),session.settings(),None if session.applied_dark is None else session.applied_dark.copy()))
        return snapshots

    def write_snapshots(self,path,snapshots):
        path=Path(path);paired=len(snapshots)>1
        targets=[path.with_name(path.stem+'-'+backend+path.suffix) if paired else path for backend,*_ in snapshots]
        with tempfile.TemporaryDirectory(dir=path.parent,prefix='.spectradesk-pair-') as temporary:
            staged=[]
            for index,(_,frame,corrected,displayed,peaks,settings,dark) in enumerate(snapshots):
                stage=Path(temporary)/(str(index)+path.suffix)
                save_measurement(stage,frame,corrected,displayed,peaks,settings,dark);staged.append(stage)
            for stage,target in zip(staged,targets):os.replace(stage,target)
        return targets

    def save_measurements(self):
        try:snapshots=self.save_snapshots()
        except ValueError as error:W.QMessageBox.information(self,'保存测量',str(error));return
        dialog=self.sessions[0].create_save_dialog()
        if len(snapshots)>1:dialog.setWindowTitle('保存两台设备测量 · 自动添加 -fla5000 / -camera')
        if dialog.exec()!=W.QDialog.DialogCode.Accepted:dialog.deleteLater();return
        path=Path(dialog.selectedFiles()[0]);selected=dialog.selectedNameFilter();dialog.deleteLater()
        if not path.suffix:path=path.with_suffix('.csv' if '*.csv' in selected else '.npz')
        targets=[path.with_name(path.stem+'-'+item[0]+path.suffix) for item in snapshots] if len(snapshots)>1 else [path]
        existing=[str(p) for p in targets if p.exists()]
        if existing and W.QMessageBox.question(self,'覆盖测量文件','覆盖以下文件？\n'+'\n'.join(existing))!=W.QMessageBox.StandardButton.Yes:return
        try:
            saved=self.write_snapshots(path,snapshots)
            W.QMessageBox.information(self,'测量已保存','\n'.join(map(str,saved)))
        except Exception as error:W.QMessageBox.warning(self,'保存失败',str(error))

    def select_view(self,index):
        if self._closing:return
        self.align_button.setVisible(index in (2,3))
        self.refresh()

    def update_device_visibility(self):
        if self._closing:return
        detected=[session.device_present or session.ready for session in self.sessions]
        key=tuple(detected)
        if getattr(self,'_device_visibility_key',None)==key:return
        self._device_visibility_key=key
        for panel,present in zip(self.device_panels,detected):
            if panel.isHidden()==bool(present):panel.setVisible(bool(present))
        if self.no_devices.isHidden()!=any(detected):self.no_devices.setVisible(not any(detected))
        visible=detected+[all(detected),all(detected)]
        current=self.tabs.currentIndex()
        with QtCore.QSignalBlocker(self.tabs):
            for index,present in enumerate(visible):
                if self.tabs.isTabVisible(index)!=bool(present):self.tabs.setTabVisible(index,bool(present))
            if any(detected):
                target=current if 0<=current<len(visible) and visible[current] else next(i for i,present in enumerate(detected) if present)
                self.tabs.setCurrentIndex(target)
        self.content.setCurrentIndex(0 if any(detected) else 1)
        self.align_button.setVisible(any(detected) and self.tabs.currentIndex() in (2,3))

    def update_device_styles(self):
        if self._closing:return
        mode=self.sessions[0].theme.currentText()
        dark=mode=='暗色' or (mode=='跟随系统' and W.QApplication.instance().styleHints().colorScheme()==QtCore.Qt.ColorScheme.Dark)
        palettes=(('#202f40','#629ed3','#a8d1f5'),('#372e25','#c99b61','#eed1a7')) if dark else (('#edf4fb','#5c8fb7','#254e73'),('#fbf3e8','#b78b52','#775122'))
        size=max(11.,W.QApplication.instance().font().pointSizeF())+.8
        active=tuple(s.ready and getattr(s,'continuous',False) for s in self.sessions)
        key=(dark,size,active)
        if getattr(self,'_device_style_key',None)==key:return
        self._device_style_key=key
        self.no_devices.setStyleSheet('color:'+('#96a1ad' if dark else '#74808b')+';font-size:12pt;')
        for i,(panel,(background,accent,title)) in enumerate(zip(self.device_panels,palettes)):
            if active[i]:
                background,accent=(('#244c6c','#83c9ff') if i==0 else ('#61472b','#ffd296')) if dark else (('#d4eaff','#277ab8') if i==0 else ('#ffe6bc','#ac681c'))
            panel.setProperty('acquiring',active[i])
            panel.setStyleSheet(f'QFrame#devicePanel{i} {{background:{background};border:1px solid {accent};border-left:4px solid {accent};border-radius:7px;}} '
                f'QFrame#devicePanel{i} QWidget {{font-size:{size:.1f}pt;}} '
                f'QLabel#deviceHeading {{color:{title};font-weight:600;}}')

    def sync_theme(self,index):
        for session in self.sessions:
            with QtCore.QSignalBlocker(session.theme):session.theme.setCurrentIndex(index)
            session.change_theme()
        self.update_device_styles()
        self.update_tab_states()
        self.plot.setBackground(self.sessions[0].plot.backgroundBrush().color())
        for plot in self.parallel_plots:plot.setBackground(self.sessions[0].plot.backgroundBrush().color())
        for axis in ('left','right','bottom'):
            source=self.sessions[0].plot.getAxis('bottom')
            self.plot.getAxis(axis).setPen(source.pen());self.plot.getAxis(axis).setTextPen(source.textPen())

    def resize_right(self):
        self.right.setGeometry(self.plot.getViewBox().sceneBoundingRect())
        self.right.linkedViewChanged(self.plot.getViewBox(),self.right.XAxis)

    def change_scale(self,*_):
        dual=self.scale.currentIndex()==1
        if dual!=self.dual_axis:
            (self.right if self.dual_axis else self.plot).removeItem(self.curves[1])
            (self.right if dual else self.plot).addItem(self.curves[1])
            self.dual_axis=dual
        self.plot.setLabel('left','FLA5000 / counts' if dual else '相对强度（各自峰值 = 1）')
        self.plot.setLabel('right','摄像头 / DN' if dual else '')
        self.plot.showAxis('right',dual)
        self.legend.clear()
        for curve,name in zip(self.curves,('FLA5000','摄像头')):self.legend.addItem(curve,name)
        self.resize_right();self.refresh();self.reset_comparison()

    def style_curve(self,curve,mode,device):
        style_spectrum_curve(curve,mode,'#459be8' if device==0 else '#e29a32')

    def fit_stable_y(self,view,curves,minimum_span,context):
        values=[]
        low,high=view.viewRange()[0]
        for curve in curves:
            if not curve.isVisible() or curve.yData is None:continue
            x=curve.xData;y=curve.yData
            selected=y[np.isfinite(y)&(x>=low)&(x<=high)]
            if selected.size:values.append(selected)
        if not values:return
        bottom=min(0.,min(float(v.min()) for v in values))
        top=max(bottom+minimum_span,max(float(v.max()) for v in values))
        span=max(top-bottom,minimum_span)
        desired=(bottom-.05*span,top+.20*span)
        now=time.monotonic();state=getattr(view,'_spectra_y_state',None)
        if state is None or state['context']!=context:
            state=dict(context=context,limits=desired,shrink=None)
        else:
            oldlo,oldhi=state['limits'];oldspan=oldhi-oldlo
            # Reserve breathing room; ignore ordinary frame-to-frame noise.
            if top>oldhi-.04*oldspan or bottom<oldlo:
                state['limits']=(min(oldlo,desired[0]),max(oldhi,desired[1]));state['shrink']=None
            elif span<oldspan*.60:
                if state['shrink'] is None:state['shrink']=now
                elif now-state['shrink']>=2:
                    state['limits']=desired;state['shrink']=None
            else:state['shrink']=None
        view._spectra_y_state=state
        view.enableAutoRange(axis='y',enable=False)
        if tuple(view.viewRange()[1])!=state['limits']:view.setYRange(*state['limits'],padding=0)

    def fit_comparison_axes(self):
        for i,plot in enumerate(self.parallel_plots):
            session=self.sessions[i]
            context=(session.display_start.value(),session.display_end.value(),session.integration.value(),session.smooth.value())
            self.fit_stable_y(plot.getViewBox(),[self.parallel_curves[i]],5. if i else 200.,context)
        if self.dual_axis:
            self.fit_stable_y(self.plot.getViewBox(),[self.curves[0]],200.,'counts')
            self.fit_stable_y(self.right,[self.curves[1]],5.,'DN')
        else:self.fit_stable_y(self.plot.getViewBox(),self.curves,1.,'normalized')

    def refresh(self,*_):
        if self._closing:return
        self.update_device_visibility()
        if self.sessions[1].frame_data is not None:
            camera=self.sessions[1];meta=camera.frame_data.get('device',{})
            context=(repr(meta.get('camera_profile',{})),camera.calibration_enabled.isChecked(),camera.nonlinearity_enabled.isChecked())
            if getattr(self,'_alignment_context',context)!=context:
                self.peak_offset=0.;self.align_button.setText('峰对齐…')
            self._alignment_context=context
        self.update_device_styles()
        self.update_tab_states()
        for session,(label,button,config,dark) in zip(self.sessions,self.device_cards):
            status_txt=session.device_status.text()
            if label.text()!=status_txt:label.setText(status_txt)
            btn_txt='断开设备' if session.ready else '连接设备'
            if button.text()!=btn_txt:button.setText(btn_txt)
            button.setEnabled(session.connect_button.isEnabled())
            if config is not None:
                config.setEnabled(session.camera_button.isEnabled())
                dark_txt=session.camera_dark.text()
                if dark.text()!=dark_txt:dark.setText(dark_txt)
                dark.setEnabled(session.camera_dark.isEnabled())

        # Skip expensive comparison plot recomputation when neither comparison tab is active
        # and the underlying session frame serials have not changed.
        tab_idx=self.tabs.currentIndex()
        frame_key=(
            tab_idx,
            self.peak_offset,
            self.dual_axis,
            self.align_bottom.isChecked(),
            tuple(c.isChecked() for c in self.visible),
            tuple(
                (
                    id(s.frame_data),
                    s.frame_data.get('index') if s.frame_data else None,
                    s.mode.currentIndex(),
                    s.smooth.value(),
                    s.display_start.value(),
                    s.display_end.value(),
                    s.calibration_enabled.isChecked(),
                    s.nonlinearity_enabled.isChecked(),
                )
                for s in self.sessions
            ),
        )
        if getattr(self,'_last_refresh_key',None)==frame_key:
            return
        self._last_refresh_key=frame_key

        for i,(session,curve,check) in enumerate(zip(self.sessions,self.curves,self.visible)):
            name=('FLA5000','摄像头')[i];f=session.frame_data
            self.style_curve(curve,session.mode.currentIndex(),i)
            self.style_curve(self.parallel_curves[i],session.mode.currentIndex(),i)
            curve.setVisible(check.isChecked())
            if f is None:
                self.parallel_curves[i].setData([],[])
                curve.setData([],[]);continue
            # Each session has already applied only its own calibration/dark/display settings.
            x=np.asarray(f['wave'])+(self.peak_offset if i else 0.);y=np.asarray(session.displayed,dtype=float).copy()
            display_peaks=[SimpleNamespace(wavelength=p.wavelength+(self.peak_offset if i else 0.)) for p in session.peaks]
            self.parallel_curves[i].setData(x,y.copy())
            limits=(session.display_start.value(),session.display_end.value())
            plot=self.parallel_plots[i]
            if limits[1]>limits[0] and getattr(plot,'_display_limits',None)!=limits:
                plot._display_limits=limits;plot.set_display_range(*limits)
            if self.align_bottom.isChecked():
                low,high=self.plot.getViewBox().viewRange()[0]
                selected=y[np.isfinite(y)&(x>=low)&(x<=high)]
                if not selected.size:selected=y[np.isfinite(y)]
                if selected.size:y-=float(selected.min())
            if not self.dual_axis:
                finite=y[np.isfinite(y)];peak=float(finite.max()) if finite.size else 0.
                if peak>0:y/=peak
                else:y[:]=0
            curve.setData(x,y)
            self.parallel_plots[i].set_spectrum_series([dict(name=name,x=x,y=session.displayed,peaks=display_peaks,unit='DN' if i else 'counts',color=('#459be8','#e29a32')[i])])
        specs=[]
        for i,(session,curve,check) in enumerate(zip(self.sessions,self.curves,self.visible)):
            if session.frame_data is not None:
                specs.append(dict(name=('FLA5000','摄像头')[i],x=curve.xData,y=curve.yData,peaks=[SimpleNamespace(wavelength=p.wavelength+(self.peak_offset if i else 0.)) for p in session.peaks],unit=(('DN' if i else 'counts')+('（显示扣底）' if self.align_bottom.isChecked() else '')) if self.dual_axis else '相对强度',view=self.right if self.dual_axis and i else self.plot.getViewBox(),visible=check.isChecked(),color=('#459be8','#e29a32')[i]))
        self.plot.set_spectrum_series(specs)
        if specs:
            low=min(float(spec['x'][0]) for spec in specs);high=max(float(spec['x'][-1]) for spec in specs)
            self.plot.set_display_range(low,high)
        self.fit_comparison_axes()
        self.align_overlay_zero()

    def bottom_alignment_changed(self,*_):
        for view in (self.plot.getViewBox(),self.right):view._spectra_y_state=None
        self.refresh()
    def align_overlay_zero(self):
        if not self.align_bottom.isChecked() or not self.dual_axis:return
        views=[self.plot.getViewBox(),self.right]
        limits=[view.viewRange()[1] for view in views]
        fraction=max(.04,max(-lo/(hi-lo) for lo,hi in limits if hi>lo))
        fraction=min(fraction,.999999)
        for view,(low,high) in zip(views,limits):
            if high>0:view.setYRange(-fraction*high/(1-fraction),high,padding=0)

    def reset_comparison(self):
        for view in [self.plot.getViewBox(),self.right]+[p.getViewBox() for p in self.parallel_plots]:view._spectra_y_state=None
        self.plot.reset_navigation()
        for plot in self.parallel_plots:plot.reset_navigation()
        self.refresh()

    def connect_all(self):
        for s in self.sessions:
            if not s.ready and not s.connecting:s.connect_request.emit()

    def start_all(self):
        for s in self.sessions:
            if s.ready and not s.busy:s.start(True)

    def stop_all(self):
        for s in self.sessions:s.stop_request.emit()

    def closeEvent(self,event):
        if self._closing:event.accept();return
        self._closing=True
        self.timer.stop();self._navigation_timer.stop()
        for session in self.sessions:session.close()
        store=QtCore.QSettings('SpectraDesk','SpectraDesk');store.setValue('workbench/geometry',self.saveGeometry());store.setValue('workbench/vertical-splitter',self.parallel.sizes());store.sync()
        event.accept()
