import os,subprocess,sys

def test_digit_wheel_and_editing_during_acquisition(tmp_path):
    code=r'''
from PySide6 import QtCore,QtWidgets as W,QtTest
from spectradesk.number_input import DigitSpinBox,DigitDoubleSpinBox
from spectradesk.workbench import Workbench
from argparse import Namespace
app=W.QApplication([])
class Wheel:
    def __init__(self,d):self.d=d
    def angleDelta(self):return QtCore.QPoint(0,self.d)
    def accept(self):pass
    def ignore(self):pass
for box,value,cursor,delta,expected in [(DigitSpinBox(),1234,2,120,1334),(DigitDoubleSpinBox(),123.4,2,120,133.4),(DigitDoubleSpinBox(),123.4,5,120,123.5),(DigitDoubleSpinBox(),99.9,2,120,100.9),(DigitDoubleSpinBox(),-12.3,3,120,-11.3)]:
 box.setRange(-9999,9999)
 if isinstance(box,W.QDoubleSpinBox):box.setDecimals(1)
 box.setValue(value);box.lineEdit().setCursorPosition(cursor);box.wheelEvent(Wheel(delta));assert abs(box.value()-expected)<1e-6,(box.value(),expected)
win=Workbench(Namespace(demo=True,smoke=None,renderer='raster'));win.show();errors=[]
def check():
 try:
  session=win.sessions[1];win.tabs.setCurrentIndex(1);session.camera_exposure_auto.setChecked(False)
  session.camera_exposure.setFocus();editor=session.camera_exposure.lineEdit();editor.selectAll();QtTest.QTest.keyClicks(editor,'25.6')
  before=editor.text();cursor=editor.cursorPosition()
  for _ in range(25):session.set_controls(True)
  assert editor.text()==before and editor.cursorPosition()==cursor,(editor.text(),before)
  QtTest.QTest.keyClick(editor,QtCore.Qt.Key.Key_Return)
  assert session.integration.value()==256
  assert session.camera_exposure.isEnabled()
 except BaseException as error:errors.append(error)
 finally:win.close();app.quit()
QtCore.QTimer.singleShot(500,check);app.exec()
if errors:raise errors[0]
'''
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(tmp_path)),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
