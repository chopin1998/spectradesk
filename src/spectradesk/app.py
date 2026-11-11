from __future__ import annotations
import argparse,json,os,sys,time
from pathlib import Path
import numpy as np
from PySide6 import QtCore,QtGui,QtWidgets as W
import pyqtgraph as pg
from .worker import Acquisition
from .plot_view import SpectrumViewBox
from .sampling_indicator import SamplingIndicator
from .analysis import analyze,display_smooth
from .storage import save_measurement
from .calibration import profile_for, correct_counts, sta_smooth

STYLE='''
QMainWindow,QWidget#root {background:#eeeef0;color:#263349;}
QWidget {color:#263349;}
QFrame#panel {background:#fafaf9;border:1px solid #d4d9df;border-radius:7px;}
QLabel#muted {color:#586777;font-size:10pt;}
QLabel#title {font-size:21pt;font-weight:600;letter-spacing:1px;color:#213a59;}
QLabel#section {color:#526477;font-size:11pt;font-weight:600;}
QLabel#metric {font-size:26pt;font-weight:500;color:#213a59;}
QLabel#deviceStatus {background:#e2ece8;color:#315c4d;border:1px solid #c4d6cd;border-radius:6px;padding:5px 10px;}
QLabel#deviceStatus[connected="false"] {background:#edf0f2;color:#586777;border-color:#d5dce2;}
QPushButton {background:#f8f9fb;border:1px solid #bcc8d3;border-radius:5px;padding:7px 10px;}
QPushButton:checked {background:#dce7f2;border-color:#6284a7;font-weight:600;}
QPushButton:hover {background:#e7edf5;border-color:#6284a7;}
QPushButton:disabled {color:#8a949f;background:#edf0f2;border-color:#d5dce2;}
QPushButton#primary {background:#345d85;color:#ffffff;border:1px solid #345d85;font-weight:600;}
QPushButton#primary:hover {background:#284c70;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:#ffffff;border:1px solid #bcc8d3;border-radius:4px;padding:6px;selection-background-color:#345d85;selection-color:#ffffff;}
QAbstractItemView {background:#fafaf9;color:#263349;alternate-background-color:#f0f3f6;selection-background-color:#dce7f2;selection-color:#213a59;}
QComboBox QAbstractItemView {background:#ffffff;color:#263349;selection-background-color:#dce7f2;selection-color:#213a59;}
QCheckBox {spacing:8px;} QCheckBox::indicator {width:18px;height:18px;}
QTableWidget {background:#fafaf9;alternate-background-color:#f0f3f6;border:0;gridline-color:#dce1e6;selection-background-color:#dce7f2;selection-color:#213a59;}
QHeaderView::section {background:#eaf0f5;color:#40566d;border:0;padding:7px;font-size:10pt;}
QStatusBar {background:#eeeef0;color:#526477;border-top:1px solid #d4d9df;}
QToolTip {background:#fffdf6;color:#263349;border:1px solid #bcc8d3;}
QScrollArea {border:0;background:#eeeef0;}
QScrollBar:vertical {background:#eeeef0;width:10px;border:0;}
QScrollBar::handle:vertical {background:#b0beca;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:#eeeef0;}
QMessageBox,QDialog {background:#fafaf9;}
'''

def apply_theme(app,mode="跟随系统"):
    dark=mode=="暗色" or (mode=="跟随系统" and app.styleHints().colorScheme()==QtCore.Qt.ColorScheme.Dark)
    # Qt6 scales logical coordinates when moving between monitors. Point-sized
    # text follows desktop DPI; do not multiply again by devicePixelRatio.
    import re
    font=app.font();base=max(11.0,font.pointSizeF() if font.pointSizeF()>0 else 11.0)
    font.setPointSizeF(base);app.setFont(font);app.setStyle('Fusion')
    palette=STYLE
    if dark:
        for a,b in {'#eeeef0':'#171c23','#263349':'#dce4ed','#fafaf9':'#212934','#d4d9df':'#3b4654','#586777':'#a2b1c2','#213a59':'#c9def2','#526477':'#aebfd0','#e2ece8':'#253e36','#315c4d':'#9ed3b5','#c4d6cd':'#466557','#f8f9fb':'#2a3543','#bcc8d3':'#536377','#e7edf5':'#36495d','#8a949f':'#788797','#edf0f2':'#252e39','#d5dce2':'#3b4654','#ffffff':'#18212c','#dce7f2':'#344d67','#f0f3f6':'#273341','#dce1e6':'#3b4654','#eaf0f5':'#2b3949','#40566d':'#c1d0df'}.items():palette=palette.replace(a,b)
        palette+='QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {selection-color:#ffffff;} QPushButton#primary {color:#ffffff;} QPushButton#running {background:#914d44;color:#ffffff;border:1px solid #b87366;}'
    else:palette+='QPushButton#running {background:#a44b3f;color:#ffffff;border:1px solid #a44b3f;}'
    accents=('QPushButton#connect {background:#315e4c;color:#ffffff;border-color:#4f8b70;} QPushButton#connect:hover {background:#3c745e;} '
             'QPushButton#disconnect {background:#83483f;color:#ffffff;border-color:#b87366;} QPushButton#disconnect:hover {background:#9c574c;}') if dark else (
             'QPushButton#connect {background:#2d7653;color:#ffffff;border-color:#2d7653;} QPushButton#connect:hover {background:#245f43;} '
             'QPushButton#disconnect {background:#a44b3f;color:#ffffff;border-color:#a44b3f;} QPushButton#disconnect:hover {background:#883d33;}')
    palette+=accents+'QPushButton#connect:disabled,QPushButton#disconnect:disabled {background:#3b4654;color:#788797;border-color:#536377;}' if dark else accents+'QPushButton#connect:disabled,QPushButton#disconnect:disabled {background:#edf0f2;color:#8a949f;border-color:#d5dce2;}'
    colors={
        'Window':('#eeeef0','#171c23'),'WindowText':('#263349','#dce4ed'),
        'Base':('#ffffff','#18212c'),'AlternateBase':('#f0f3f6','#273341'),
        'Text':('#263349','#dce4ed'),'Button':('#f8f9fb','#2a3543'),
        'ButtonText':('#263349','#dce4ed'),'Highlight':('#345d85','#344d67'),
        'HighlightedText':('#ffffff','#ffffff'),'ToolTipBase':('#fffdf6','#212934'),
        'ToolTipText':('#263349','#dce4ed'),'PlaceholderText':('#586777','#a2b1c2'),
        'Light':('#ffffff','#536377'),'Midlight':('#eaf0f5','#3b4654'),
        'Mid':('#bcc8d3','#3b4654'),'Dark':('#8a949f','#10151b'),
        'Shadow':('#586777','#0c1015'),'Link':('#245b8f','#84b9ed'),
        'LinkVisited':('#684799','#be9fed')}
    qt_palette=QtGui.QPalette()
    for role,values in colors.items():
        qt_palette.setColor(getattr(QtGui.QPalette.ColorRole,role),QtGui.QColor(values[int(dark)]))
    for role in ('WindowText','Text','ButtonText'):
        qt_palette.setColor(QtGui.QPalette.ColorGroup.Disabled,getattr(QtGui.QPalette.ColorRole,role),QtGui.QColor('#788797' if dark else '#8a949f'))
    app.setPalette(qt_palette)
    app.setStyleSheet(re.sub(r'font-size:(\d+)pt',lambda m:f'font-size:{float(m[1])*base/11:.2f}pt',palette))
    return dark


class ThemeSelector(W.QPushButton):
    currentIndexChanged=QtCore.Signal(int)
    currentTextChanged=QtCore.Signal(str)
    modes=('跟随系统','浅色','暗色')
    def __init__(self,parent=None):
        super().__init__(parent);self.index=0
        self.setText('主题：跟随系统');self.setToolTip('点击切换：跟随系统 → 浅色 → 暗色')
        self.clicked.connect(lambda:self.setCurrentIndex((self.index+1)%len(self.modes)))
    def currentIndex(self):return self.index
    def currentText(self):return self.modes[self.index]
    def setCurrentIndex(self,index):
        if index not in range(len(self.modes)):index=0
        self.index=index;self.setText('主题：'+self.modes[index])
        self.currentIndexChanged.emit(index);self.currentTextChanged.emit(self.modes[index])


def acquire_instance_lock(directory=None):
    directory=directory or QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.RuntimeLocation)
    if not directory:directory=QtCore.QDir.tempPath()
    lock=QtCore.QLockFile(str(Path(directory)/f'spectradesk-{os.getuid()}.lock'))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(0) else None


class Window(W.QMainWindow):
    connect_request=QtCore.Signal();disconnect_request=QtCore.Signal()
    integration_request=QtCore.Signal(int);average_request=QtCore.Signal(int);start_request=QtCore.Signal(int,int,bool);stop_request=QtCore.Signal();auto_request=QtCore.Signal()
    def __init__(self,args):
        super().__init__();self.args=args;self.frame_data=None;self.dark=None;self.pending_dark=False;self.ready=False;self.busy=False;self.last_time=None;self.sampling_context=None;self.capture_started_at=None;self.peaks=[];self.profile=None;self.processing={};self.calibration_error=None;self.device_present=bool(args.demo);self.connecting=False
        self.setWindowTitle('SpectraDesk · 光谱测量工作台');area=W.QApplication.primaryScreen().availableGeometry();self.resize(min(1560,int(area.width()*.94)),min(1000,int(area.height()*.94)));self.setMinimumSize(1180,760)
        self.build();self.restore_settings()
        self.thread=QtCore.QThread(self);self.worker=Acquisition(args.demo);self.worker.moveToThread(self.thread)
        self.connect_request.connect(self.worker.connect_device);self.disconnect_request.connect(self.worker.disconnect_device)
        self.average_request.connect(self.worker.set_average);self.integration_request.connect(self.worker.set_integration);self.start_request.connect(self.worker.start);self.stop_request.connect(self.worker.stop);self.auto_request.connect(self.worker.auto)
        self.worker.device_available.connect(self.on_device_available);self.worker.connection_changed.connect(self.on_connection_changed);self.worker.connected.connect(self.on_connected);self.worker.capture_started.connect(self.on_capture_started);self.worker.frame.connect(self.on_frame);self.worker.state.connect(self.on_state);self.worker.error.connect(self.on_error);self.worker.auto_done.connect(self.on_auto);self.worker.integration_changed.connect(self.update_integration)
        self.thread.finished.connect(self.worker.deleteLater);self.thread.start()
        self.set_controls(False)
        QtCore.QTimer.singleShot(150,self.connect_request.emit)
        if args.smoke:QtCore.QTimer.singleShot(15000,self.smoke_timeout)
    def label(self,text,kind=None):
        w=W.QLabel(text)
        if kind:w.setObjectName(kind)
        return w
    def card(self):
        w=W.QFrame();w.setObjectName('panel');layout=W.QVBoxLayout(w);layout.setContentsMargins(16,14,16,14);layout.setSpacing(10);return w,layout
    def build(self):
        root=W.QWidget();root.setObjectName('root');self.setCentralWidget(root);outer=W.QVBoxLayout(root);outer.setContentsMargins(24,18,24,12);outer.setSpacing(16)
        header=W.QHBoxLayout();brand=W.QVBoxLayout();brand.setSpacing(0);brand.addWidget(self.label('SPECTRADESK','title'));header.addLayout(brand);header.addStretch()
        self.theme=ThemeSelector();self.theme.currentTextChanged.connect(self.change_theme);header.addWidget(self.theme)
        self.info_button=W.QPushButton('设备与校准');self.info_button.clicked.connect(self.show_info);self.info_button.setEnabled(False);header.addWidget(self.info_button)
        self.save_button=W.QPushButton('保存测量…');self.save_button.clicked.connect(self.save);self.save_button.setEnabled(False);header.addWidget(self.save_button);outer.addLayout(header)
        body=W.QHBoxLayout();body.setSpacing(16);outer.addLayout(body,1)
        sidebar=W.QWidget();sidebar.setObjectName('root');sidebar.setFixedWidth(max(310,self.fontMetrics().horizontalAdvance('STA 名义毫秒 · ×50 换算')+80));side=W.QVBoxLayout(sidebar);side.setContentsMargins(0,0,0,0);side.setSpacing(12);side.setSizeConstraint(W.QLayout.SizeConstraint.SetMinimumSize)
        panel,l=self.card();l.addWidget(self.label('设备','section'));self.device_label=self.label('FLIGHT FLA5000');self.device_label.setStyleSheet('font-weight:600');l.addWidget(self.device_label)
        self.serial_label=self.label('USB  f0d0:5001 · 2048 像素','muted');l.addWidget(self.serial_label)
        self.device_status=self.label('模拟模式' if self.args.demo else '正在寻找光谱仪…','deviceStatus');self.device_status.setWordWrap(True);l.addWidget(self.device_status)
        self.connect_button=W.QPushButton('连接光谱仪');self.connect_button.clicked.connect(self.toggle_connection);l.addWidget(self.connect_button);side.addWidget(panel)
        panel,l=self.card();l.addWidget(self.label('采集控制','section'))
        self.integration_label=self.label('积分时间 · 250');l.addWidget(self.integration_label)
        self.integration=W.QSpinBox();self.integration.setRange(15,65535);self.integration.setValue(250);self.integration.setKeyboardTracking(False);self.integration.valueChanged.connect(self.integration_request.emit);self.integration.valueChanged.connect(self.update_integration_label);l.addWidget(self.integration)
        self.auto_button=W.QPushButton('自动选择积分');self.auto_button.clicked.connect(self.request_auto);l.addWidget(self.auto_button)
        row=W.QHBoxLayout();row.addWidget(self.label('平均帧数'));self.average=W.QSpinBox();self.average.setRange(1,64);self.average.setValue(2);self.average.setKeyboardTracking(False);self.average.valueChanged.connect(self.average_request.emit);self.average.setToolTip('这里填写实际采集帧数。已验证 STA 的“平均1”读取两帧，对照时这里选2。');row.addWidget(self.average);l.addLayout(row)
        row=W.QHBoxLayout();self.single=W.QPushButton('单次');self.single.clicked.connect(lambda:self.start(False));self.run=W.QPushButton('连续采集');self.run.setObjectName('primary');self.run.clicked.connect(self.toggle_acquisition);row.addWidget(self.single);row.addWidget(self.run);l.addLayout(row)
        side.addWidget(panel)
        panel,l=self.card();l.addWidget(self.label('显示','section'));self.mode=W.QComboBox();self.mode.addItems(['专业单色线','连续彩虹线','彩虹填充谱']);self.mode.currentIndexChanged.connect(self.render);l.addWidget(self.mode)
        row=W.QHBoxLayout();row.addWidget(self.label('平滑'));self.smooth=W.QSpinBox();self.smooth.setRange(0,50);self.smooth.setSpecialValueText('关闭');self.smooth.setValue(1);self.smooth.setToolTip('N 对应 2N 个点，仅影响显示与STA对照导出；分析使用未平滑校正数据。设备校正模式复现STA尾部不平滑规则。');self.smooth.valueChanged.connect(self.render);row.addWidget(self.smooth);l.addLayout(row)
        self.overlay=W.QCheckBox('叠加未平滑曲线');self.overlay.setChecked(True);self.overlay.toggled.connect(self.render);l.addWidget(self.overlay)
        l.addWidget(self.label('显示波长范围 / nm'))
        row=W.QHBoxLayout();self.display_start=W.QDoubleSpinBox();self.display_end=W.QDoubleSpinBox()
        for box,value in ((self.display_start,280),(self.display_end,973)):
            box.setDecimals(1);box.setRange(200,1100);box.setValue(value);box.setKeyboardTracking(False);box.valueChanged.connect(self.render);row.addWidget(box)
        l.addLayout(row)
        self.reset_view=W.QPushButton('完整波段');self.reset_view.clicked.connect(self.reset_plot);l.addWidget(self.reset_view);side.addWidget(panel)
        panel,l=self.card();l.addWidget(self.label('设备校正','section'))
        self.calibration_enabled=W.QCheckBox('应用设备校正');self.calibration_enabled.setChecked(True);self.calibration_enabled.toggled.connect(self.render);l.addWidget(self.calibration_enabled)
        self.nonlinearity_enabled=W.QCheckBox('非线性修正');self.nonlinearity_enabled.setChecked(True);self.nonlinearity_enabled.toggled.connect(self.render);l.addWidget(self.nonlinearity_enabled)
        self.calibration_label=self.label('连接后按序列号匹配校准档案','muted');self.calibration_label.setWordWrap(True);l.addWidget(self.calibration_label);side.addWidget(panel)
        side.addStretch();scroll=W.QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setFixedWidth(sidebar.width()+16);scroll.setWidget(sidebar);body.addWidget(scroll)
        main=W.QVBoxLayout();main.setSpacing(12);body.addLayout(main,1)
        cards=W.QHBoxLayout();self.metric_labels=[]
        for title,unit in [('主峰波长','nm'),('半高全宽 FWHM','nm'),('峰顶强度','counts')]:
            card,cl=self.card();cl.setSpacing(3);cl.addWidget(self.label(title,'section'));metric=self.label('—','metric');cl.addWidget(metric);cl.addWidget(self.label(unit,'muted'));self.metric_labels.append(metric);cards.addWidget(card)
        main.addLayout(cards)
        graph,l=self.card();graph.setMinimumHeight(220);l.setContentsMargins(12,10,12,10)
        topline=W.QHBoxLayout();topline.addWidget(self.label('光谱 / SPECTRUM','section'));topline.addStretch();self.cursor_label=self.label('移动鼠标查看波长与强度','muted');topline.addWidget(self.cursor_label);l.addLayout(topline)
        pg.setConfigOptions(antialias=False,background='#ffffff',foreground='#526477')
        self.spectrum_view=SpectrumViewBox();self.plot=pg.PlotWidget(viewBox=self.spectrum_view);self.plot.setLabel('bottom','Wavelength',units='nm');self.plot.setLabel('left','Intensity',units='counts');self.plot.showGrid(x=True,y=True,alpha=.13);self.plot.setMouseEnabled(x=False,y=False);self.plot.setMenuEnabled(False)
        self.plot.getAxis('left').enableAutoSIPrefix(False);
        for name in ('left','bottom'):
            axis=self.plot.getAxis(name);axis.setTickFont(self.font());axis.label.setFont(self.font())
        self.plot.setXRange(350,950,padding=0);self.plot.setYRange(0,16000,padding=0)
        self.raw_curve=self.plot.plot(pen=pg.mkPen('#abb7c4',width=1));self.curve=self.plot.plot(pen=pg.mkPen('#245b8f',width=1.8));self.markers=pg.ScatterPlotItem(size=7,brush='#a96820',pen=None);self.plot.addItem(self.markers)
        # Raster drawLines is much cheaper for dense gradient spectra than drawPath.
        self.curve.curve.setSegmentedLineMode('on');self.raw_curve.curve.setSegmentedLineMode('on')
        self.halfline=self.plot.plot(pen=pg.mkPen('#a96820',width=1,style=QtCore.Qt.PenStyle.DashLine))
        self.cursor_wave=None
        self.cursor_marker=pg.ScatterPlotItem(size=11,symbol='o',pxMode=True,brush='#ffe066',pen=pg.mkPen('#805615',width=1.5))
        self.cursor_marker.setZValue(50);self.cursor_marker.hide();self.plot.addItem(self.cursor_marker,ignoreBounds=True)
        self.plot.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor);self.spectrum_view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.plot.viewport().installEventFilter(self);self.plot.scene().sigMouseMoved.connect(self.mouse_moved)
        self.baseline=pg.InfiniteLine(pos=0,angle=0,movable=False,pen=pg.mkPen('#8a98a5',style=QtCore.Qt.PenStyle.DashLine));self.plot.addItem(self.baseline)
        l.addWidget(self.plot,1)
        self.navigation_label=self.label('','muted');self.navigation_label.setWordWrap(True);l.addWidget(self.navigation_label)
        self.spectrum_view.sigRangeChanged.connect(self.update_navigation)
        self.warning_label=self.label('','muted');self.warning_label.setWordWrap(True);self.warning_label.hide();l.addWidget(self.warning_label);main.addWidget(graph,1)
        panel,l=self.card();top=W.QHBoxLayout();top.addWidget(self.label('峰值分析','section'));top.addStretch();top.addWidget(self.label('分析范围 / nm','muted'))
        self.range_start=W.QDoubleSpinBox();self.range_end=W.QDoubleSpinBox()
        for box,value in [(self.range_start,350),(self.range_end,900)]:box.setDecimals(1);box.setRange(200,1100);box.setValue(value);box.setFixedWidth(max(118,self.fontMetrics().horizontalAdvance('1100.0')+48));box.valueChanged.connect(self.render);top.addWidget(box)
        l.addLayout(top);self.table=W.QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['峰位 / nm','强度 / counts','FWHM / nm','质量提示']);self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch);self.table.verticalHeader().hide();self.table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows);self.table.verticalHeader().setDefaultSectionSize(self.fontMetrics().height()+12);self.table.setMinimumHeight(120);self.table.setMaximumHeight(200);self.table.setAlternatingRowColors(True);l.addWidget(self.table)
        main.addWidget(panel)
        self.status=self.statusBar();self.status.showMessage('正在寻找光谱仪…')
        self.sampling_indicator=SamplingIndicator();self.status.addPermanentWidget(self.sampling_indicator)
        self.measure_status=self.label('— 帧  ·  — Hz','muted');self.status.addPermanentWidget(self.measure_status)
    def set_controls(self,ready):
        self.ready=ready
        self.device_status.setProperty("connected",ready);self.device_status.style().unpolish(self.device_status);self.device_status.style().polish(self.device_status)
        self.info_button.setEnabled(ready)
        self.single.setEnabled(ready and not self.busy)
        self.auto_button.setEnabled(ready and not getattr(self,'auto_busy',False))
        self.run.setEnabled(ready)
        self.connect_button.setEnabled((ready or self.device_present) and not self.connecting and not getattr(self,'auto_busy',False))
        running=getattr(self,'continuous',False) or getattr(self,'auto_busy',False);self.run.setText('取消自动积分' if getattr(self,'auto_busy',False) else ('停止采集' if running else '连续采集'));self.run.setObjectName('running' if running else 'primary');self.run.style().unpolish(self.run);self.run.style().polish(self.run)
        self.integration.setEnabled(not getattr(self,'auto_busy',False))
        self.average.setEnabled(not getattr(self,'auto_busy',False))
        self.connect_button.setText('断开设备' if ready else '连接光谱仪')
        self.connect_button.setObjectName('disconnect' if ready else 'connect')
        self.connect_button.style().unpolish(self.connect_button);self.connect_button.style().polish(self.connect_button)
    def show_info(self):
        d=self.connection;meta=d['meta'];dialog=W.QDialog(self);dialog.setWindowTitle('设备与波长校准');dialog.resize(580,520);layout=W.QVBoxLayout(dialog)
        text=W.QLabel(f"{meta['model']}  ·  SN {meta['serial']}\n固件 {meta['firmware']}  ·  2048 像素\n波长映射：设备标定点之间分段线性插值；两端为外推值。");text.setWordWrap(True);layout.addWidget(text)
        table=W.QTableWidget(len(meta['anchors']),2);table.setHorizontalHeaderLabels(['像素位置','标定波长 / nm']);table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch);table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        for i,a in enumerate(meta['anchors']):
            table.setItem(i,0,W.QTableWidgetItem(f"{a['pixel']:.1f}"));table.setItem(i,1,W.QTableWidgetItem(f"{a['wavelength_nm']:.5f}"))
        layout.addWidget(table)
        label=W.QLabel('本页只读。设备校正包含暗背景模板、自动扣暗、分段非线性修正。仅匹配序列号、固件和波长标定时启用；仍为计数，不是绝对辐射定标。不提供校准写入及 GPIO 控制。');label.setWordWrap(True);layout.addWidget(label)
        close=W.QPushButton('关闭');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()
    def toggle_connection(self):
        if self.connecting:return
        if self.ready:
            self.connecting=True;self.disconnect_request.emit();self.set_controls(False)
        elif self.device_present:
            self.connecting=True;self.device_status.setText('正在连接…');self.set_controls(False);self.connect_request.emit()
    @QtCore.Slot(bool)
    def on_device_available(self,available):
        self.device_present=available
        if not self.ready:
            if not available:self.connecting=False
            self.device_status.setText('已找到设备 · 未连接' if available else '未找到光谱仪')
        self.set_controls(self.ready)
    @QtCore.Slot(bool)
    def on_connection_changed(self,ready):
        self.connecting=False
        if ready:self.device_present=True
        if not ready:
            self.auto_busy=False;self.continuous=False;self.busy=False;self.last_time=None;self.sampling_context=None;self.capture_started_at=None;self.sampling_indicator.reset()
            self.device_status.setText('已找到设备 · 未连接' if self.device_present else '未找到光谱仪');self.serial_label.setText('设备未连接')
            self.calibration_label.setText('连接后按序列号匹配校准档案')
            self.calibration_enabled.setEnabled(False);self.nonlinearity_enabled.setEnabled(False)
            self.measure_status.setText('已停止 · 保留上次测量' if self.frame_data is not None else '— 帧  ·  — Hz')
            self.clear_cursor_marker()
        self.set_controls(ready)
    @QtCore.Slot(object)
    def on_connected(self,data):
        self.connection=data;self.device_label.setText(data['meta']['model']);self.serial_label.setText(f"SN {data['meta']['serial']}  ·  {data['meta']['firmware']}");self.set_controls(True)
        self.device_status.setText('模拟数据 · 非实测' if data['demo'] else 'USB 已连接')
        self.profile=None;self.calibration_error=None;self.initial_fit_done=False
        try:self.profile=profile_for(data['meta'])
        except (ValueError,KeyError,OSError) as e:self.calibration_error=str(e)
        self.calibration_enabled.setEnabled(self.profile is not None);self.nonlinearity_enabled.setEnabled(self.profile is not None)
        self.calibration_label.setText(('校准档案已匹配 · 暗背景＋非线性' if self.profile else '无匹配档案 · 使用原始计数') if not self.calibration_error else '校准档案无效：'+self.calibration_error)
        self.integration_request.emit(self.integration.value())
        if self.args.smoke:self.start(False)
    @QtCore.Slot(str)
    def on_state(self,text):
        self.auto_busy=text.startswith('自动积分 ·');self.busy=text in ('连续采集中','单次采集中') or self.auto_busy
        if not self.auto_busy:self.continuous=text=='连续采集中'
        self.set_controls(self.ready);self.status.showMessage(text)
        if not self.busy or self.auto_busy:
            self.sampling_indicator.stop();self.last_time=None
        if text=="USB 已断开":self.device_status.setText(text)
    @QtCore.Slot(str)
    def on_error(self,text):
        self.pending_dark=False;self.connecting=False;self.sampling_indicator.stop();self.last_time=None
        self.device_status.setText('连接异常');self.status.showMessage(text);self.warning_label.setText(text);self.warning_label.show();self.busy=False;self.set_controls(False)
        if self.args.smoke:print(text,file=sys.stderr);self.args.failed=True;self.close()
    def start(self,continuous):
        p=self.integration.value();self.last_time=None
        self.busy=True;self.set_controls(self.ready);self.start_request.emit(p,self.average.value(),continuous)
    @QtCore.Slot(int)
    def update_integration_label(self,parameter):
        self.integration_label.setText(f'积分时间 · {parameter}')
    @QtCore.Slot(int)
    def update_integration(self,parameter):
        with QtCore.QSignalBlocker(self.integration):
            self.integration.setValue(parameter)
            self.integration.lineEdit().setText(str(self.integration.value()))
        self.update_integration_label(self.integration.value())
    @QtCore.Slot(int,str)
    def on_auto(self,p,text):
        self.update_integration(p);self.persist_settings();self.warning_label.setText(text);self.warning_label.setVisible(bool(text))
    @QtCore.Slot(float,int,int)
    def on_capture_started(self,started,parameter,average):
        context=(parameter,average)
        changed=context!=self.sampling_context
        if changed:self.last_time=None
        self.sampling_context=context;self.capture_started_at=started
        self.sampling_indicator.begin(started,reset=changed)
        if self.sampling_indicator.period is None:self.measure_status.setText('采样中…')
    @QtCore.Slot(object)
    def on_frame(self,frame):
        self.frame_data=frame;self.save_button.setEnabled(True)
        now=time.monotonic() if self.capture_started_at is None else self.capture_started_at+frame['elapsed']
        period=max(frame['elapsed'],1e-6) if self.last_time is None else max(now-self.last_time,1e-6)
        self.last_time=now;self.sampling_indicator.complete(period)
        rate=f'  ·  {1/period:.1f} Hz' if period<=.2 else ''
        self.measure_status.setText(f"{frame['index']} 帧{rate}  ·  读取 {frame['elapsed']*1000:.1f} ms")
        self.render()
        if self.args.smoke and not getattr(self,'smoke_scheduled',False):
            self.smoke_scheduled=True;QtCore.QTimer.singleShot(200,self.finish_smoke)
    def corrected_data(self):
        f=self.frame_data;y=f['mean'].copy();dark=None
        self.processing=dict(method='raw' if dark is None else 'manual-dark',nonlinearity=False)
        if self.calibration_enabled.isChecked() and self.profile and self.profile.matches(f['device']):
            y,self.processing=correct_counts(y,self.profile,nonlinear=self.nonlinearity_enabled.isChecked(),manual_dark=dark)
        elif dark is not None:y-=dark
        return y,dark
    def render(self,*_):
        if self.frame_data is None:return
        f=self.frame_data;x=f['wave'];y,dark=self.corrected_data();shown=sta_smooth(y,self.smooth.value()) if 'profile_sha256' in self.processing else display_smooth(y,self.smooth.value())
        self.corrected=y;self.displayed=shown;self.applied_dark=dark
        self.raw_curve.setData(x,y if self.overlay.isChecked() and self.smooth.value() else np.full_like(y,np.nan))
        index=self.mode.currentIndex()
        style_key=(index,self.theme.currentText(),W.QApplication.instance().styleHints().colorScheme())
        if getattr(self,'curve_style_key',None)!=style_key:
            self.curve_style_key=style_key
            if index:
                gradient=QtGui.QLinearGradient(380,0,780,0)
                for value,color in [(0,'#9068e9'),(.15,'#6588ff'),(.25,'#48d5ec'),(.375,'#78e59d'),(.5,'#e5e472'),(.625,'#f3aa67'),(.8,'#ed6e75'),(1,'#ae556b')]:gradient.setColorAt(value,QtGui.QColor(color))
                pen=QtGui.QPen(QtGui.QBrush(gradient),1.8);pen.setCosmetic(True);self.curve.setPen(pen)
                if index==2:
                    for stop,color in gradient.stops():color.setAlpha(65);gradient.setColorAt(stop,color)
                    self.curve.setFillLevel(0);self.curve.setBrush(QtGui.QBrush(gradient))
                else:self.curve.setFillLevel(None)
            else:self.curve.setPen(pg.mkPen('#84b9ed' if self.theme.currentText()=='暗色' or (self.theme.currentText()=='跟随系统' and W.QApplication.instance().styleHints().colorScheme()==QtCore.Qt.ColorScheme.Dark) else '#245b8f',width=1.8));self.curve.setFillLevel(None)
        self.curve.setData(x,shown)
        self.fit_display()
        self.update_cursor_marker()
        self.peaks=analyze(x,y,self.range_start.value(),self.range_end.value())
        clipped=bool(np.any((32767-f['adc_frames'].astype(np.int32))[:,10:2041]>=16500))
        if clipped:
            peak_max=float(np.max(y))
            for p in self.peaks:
                if p.intensity>=.85*peak_max:p.fwhm=None;p.warning='原始帧可能削顶，半高宽无效'
        self.markers.setData([p.wavelength for p in self.peaks],[p.intensity for p in self.peaks])
        if self.peaks:
            p=self.peaks[0];self.metric_labels[0].setText(f'{p.wavelength:.2f}');self.metric_labels[1].setText('—' if p.fwhm is None else f'{p.fwhm:.2f}');self.metric_labels[2].setText(f'{p.intensity:,.0f}')
            if p.fwhm is not None:self.halfline.setData([p.left,p.right],[p.baseline+(p.intensity-p.baseline)/2]*2)
            else:self.halfline.setData([],[])
        else:
            for label in self.metric_labels:label.setText('—')
            self.halfline.setData([],[])
        self.table.setRowCount(len(self.peaks))
        for row,p in enumerate(self.peaks):
            for col,text in enumerate([f'{p.wavelength:.2f}',f'{p.intensity:.1f}','—' if p.fwhm is None else f'{p.fwhm:.2f}',p.warning or '可分析']):self.table.setItem(row,col,W.QTableWidgetItem(text))
        notes=[]
        if clipped:notes.insert(0,'⚠ 原始帧接近实测削顶水平')
        if self.range_start.value()>=self.range_end.value():notes.insert(0,'分析起点必须小于终点')
        self.warning_label.setText('  ·  '.join(notes));self.warning_label.setVisible(bool(notes))
    def update_navigation(self,*args):
        low,high=self.spectrum_view.viewRange()[0]
        self.navigation_label.setText(f'显示 {low:.1f}–{high:.1f} nm')
    def fit_display(self):
        if self.frame_data is None:return
        x=self.frame_data['wave'];y=self.displayed
        low=max(float(x.min()),self.display_start.value());high=min(float(x.max()),self.display_end.value())
        if high<=low:
            self.navigation_label.setText('显示波长无效：下限须小于上限，且在设备波段内');return
        mask=(x>=low)&(x<=high)&np.isfinite(y)
        if not np.any(mask):
            self.navigation_label.setText('所选范围内没有采样点');return
        values=y[mask];bottom=min(0.,float(values.min()));top=max(bottom+200.,float(values.max()))
        # A display-only floor keeps dark noise from filling the entire plot.
        context=(low,high,self.frame_data['parameter'],self.smooth.value(),self.processing.get('method'),self.processing.get('nonlinearity'))
        now=time.monotonic();desired=(bottom-max(1.,(top-bottom)*.05),top+max(1.,(top-bottom)*.05))
        if getattr(self,'axis_context',None)!=context:
            self.axis_context=context;self.axis_limits=desired;self.axis_shrink_since=None
        else:
            oldlo,oldhi=self.axis_limits
            if top>oldhi or bottom<oldlo:
                self.axis_limits=(min(oldlo,desired[0]),max(oldhi,top*1.1));self.axis_shrink_since=None
            elif top<oldhi*.65:
                if self.axis_shrink_since is None:self.axis_shrink_since=now
                elif now-self.axis_shrink_since>=2:self.axis_limits=desired;self.axis_shrink_since=None
            else:self.axis_shrink_since=None
        self.plot.setXRange(low,high,padding=0);self.plot.setYRange(*self.axis_limits,padding=0)
        self.update_navigation()
    def reset_plot(self):
        if self.frame_data is not None:
            x=self.frame_data['wave']
            for box,value in ((self.display_start,float(x.min())),(self.display_end,float(x.max()))):
                box.blockSignals(True);box.setValue(value);box.blockSignals(False)
            self.fit_display()
    def clear_cursor_marker(self):
        self.cursor_wave=None;self.cursor_marker.hide()
        self.cursor_label.setText('移动鼠标查看波长与强度')
    def update_cursor_marker(self):
        if self.cursor_wave is None or self.frame_data is None:return
        wave=self.frame_data['wave'];low,high=self.spectrum_view.viewRange()[0]
        if not max(low,float(wave[0]))<=self.cursor_wave<=min(high,float(wave[-1])):
            self.clear_cursor_marker();return
        intensity=float(np.interp(self.cursor_wave,wave,self.displayed))
        if not np.isfinite(intensity):
            self.clear_cursor_marker();return
        self.cursor_marker.setData([self.cursor_wave],[intensity]);self.cursor_marker.show()
        self.cursor_label.setText(f'{self.cursor_wave:.2f} nm  ·  {intensity:.1f} counts')
    def mouse_moved(self,pos):
        if self.frame_data is None or not self.spectrum_view.sceneBoundingRect().contains(pos):
            self.clear_cursor_marker();return
        self.cursor_wave=self.spectrum_view.mapSceneToView(pos).x();self.update_cursor_marker()
    def eventFilter(self,watched,event):
        if event.type()==QtCore.QEvent.Type.Leave and hasattr(self,'plot') and watched is self.plot.viewport():
            self.clear_cursor_marker()
        return super().eventFilter(watched,event)
    def request_auto(self):
        if not self.ready or getattr(self,'auto_busy',False):return
        self.auto_busy=True;self.busy=True;self.set_controls(True);self.auto_request.emit()
    def toggle_acquisition(self):
        if getattr(self,'auto_busy',False):
            self.run.setEnabled(False);self.stop_request.emit();return
        if getattr(self,'continuous',False):self.stop_request.emit()
        else:self.start(True)
    def persist_settings(self,*_):
        if getattr(self,'restoring',False):return
        store=QtCore.QSettings('SpectraDesk','SpectraDesk')
        for name in ('integration','average','smooth','display_start','display_end','range_start','range_end'):store.setValue(name,getattr(self,name).value())
        for name in ('mode','theme'):store.setValue(name,getattr(self,name).currentIndex())
        for name in ('overlay','calibration_enabled','nonlinearity_enabled'):store.setValue(name,getattr(self,name).isChecked())
        store.sync()
    def restore_settings(self):
        self.restoring=True;store=QtCore.QSettings('SpectraDesk','SpectraDesk')
        for name in ('integration','average','smooth','display_start','display_end','range_start','range_end'):
            box=getattr(self,name)
            if store.contains(name):box.setValue(float(store.value(name)) if isinstance(box,W.QDoubleSpinBox) else int(store.value(name)))
            box.valueChanged.connect(self.persist_settings)
        for name in ('mode','theme'):
            box=getattr(self,name);box.setCurrentIndex(int(store.value(name,0)));box.currentIndexChanged.connect(self.persist_settings)
        for name in ('overlay','calibration_enabled','nonlinearity_enabled'):
            box=getattr(self,name);box.setChecked(store.value(name,True,type=bool));box.toggled.connect(self.persist_settings)
        self.restoring=False;self.change_theme()
        W.QApplication.instance().styleHints().colorSchemeChanged.connect(lambda *_:self.change_theme())
    def change_theme(self,*_):
        if not hasattr(self,'plot'):return
        dark=apply_theme(W.QApplication.instance(),self.theme.currentText());self.plot.setBackground('#18212c' if dark else '#ffffff')
        self.cursor_marker.setPen(pg.mkPen('#ffffff' if dark else '#805615',width=1.5))
        for name in ('left','bottom'):
            axis=self.plot.getAxis(name);axis.setPen('#aebfd0' if dark else '#526477');axis.setTextPen('#aebfd0' if dark else '#526477')
        self.render()
    def settings(self):return dict(calibration=self.processing,calibration_profile=self.profile.data if 'profile_sha256' in self.processing else None,smoothing='STA display-only',smooth_count=self.smooth.value(),plot_mode=self.mode.currentText(),analysis_range_nm=[self.range_start.value(),self.range_end.value()],fwhm_baseline='10th percentile of full spectrum',integration_mode="STA integer parameter",display_range_nm=[self.display_start.value(),self.display_end.value()],dark_metadata=None if self.applied_dark is None else {k:v for k,v in self.dark.items() if k!='counts'})
    def create_save_dialog(self):
        dialog=W.QFileDialog(self,'保存测量')
        dialog.setOption(W.QFileDialog.Option.DontUseNativeDialog,True)
        dialog.setAcceptMode(W.QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilters(['完整测量 (*.npz)','数据表 (*.csv)'])
        dialog.selectFile('spectrum.npz')
        return dialog
    def save(self):
        if self.frame_data is None:return
        dialog=self.create_save_dialog()
        accepted=dialog.exec()==W.QDialog.DialogCode.Accepted
        files=dialog.selectedFiles();selected=dialog.selectedNameFilter();dialog.deleteLater()
        if not accepted or not files:return
        path=files[0]
        if not Path(path).suffix:path+='.csv' if '*.csv' in selected else '.npz'
        try:save_measurement(path,self.frame_data,self.corrected,self.displayed,self.peaks,self.settings(),self.applied_dark);self.status.showMessage(f'已保存：{path}')
        except Exception as e:W.QMessageBox.warning(self,'保存失败',str(e))
    def finish_smoke(self):
        if getattr(self.args,'finished',False):return
        self.args.finished=True;self.stop_request.emit();self.reset_plot();self.mode.setCurrentIndex(2);self.smooth.setValue(2)
        path=Path(self.args.smoke);path.mkdir(parents=True,exist_ok=True)
        save_measurement(path/'measurement.npz',self.frame_data,self.corrected,self.displayed,self.peaks,self.settings(),self.applied_dark)
        self.grab().save(str(path/'screenshot.png'));print(json.dumps(dict(device=self.frame_data['device'],peaks=[p.__dict__ for p in self.peaks],pixels=len(self.frame_data['wave'])),ensure_ascii=False),flush=True);self.close()
    def smoke_timeout(self):
        if not getattr(self.args,'finished',False):self.args.failed=True;print('Smoke timeout',file=sys.stderr);self.close()
    def closeEvent(self,event):
        self.sampling_indicator.stop()
        self.persist_settings()
        self.thread.requestInterruption()
        if self.thread.isRunning():
            QtCore.QMetaObject.invokeMethod(self.worker,'disconnect_device',QtCore.Qt.ConnectionType.BlockingQueuedConnection)
            self.thread.quit();self.thread.wait(5000)
        event.accept()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');parser.add_argument('--connect',action='store_true',help='Connect on startup (now the default; does not start acquisition)');parser.add_argument('--smoke',help='Save screenshot and one measurement then exit');args=parser.parse_args()
    app=W.QApplication(sys.argv[:1]);app.setApplicationName('SpectraDesk')
    instance_lock=acquire_instance_lock()
    if instance_lock is None:
        print('SpectraDesk 已在运行，或无法取得运行锁。',file=sys.stderr);return 1
    apply_theme(app)
    app.setQuitOnLastWindowClosed(False)
    win=Window(args);win.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose);win.destroyed.connect(app.quit);win.show();app.exec();return 1 if getattr(args,'failed',False) else 0
if __name__=='__main__':sys.exit(main())
