"""Numeric inputs whose mouse wheel changes the digit left of the caret."""
from PySide6 import QtWidgets as W

class DigitWheel:
    def wheelEvent(self,event):
        if not self.isEnabled():event.ignore();return
        delta=event.angleDelta().y()
        if not delta:event.ignore();return
        remainder=getattr(self,'_wheel_remainder',0)+delta
        steps=int(remainder/120);self._wheel_remainder=remainder-steps*120
        event.accept()
        if not steps:return
        editor=self.lineEdit();text=editor.text();position=editor.cursorPosition()
        decimal=self.locale().decimalPoint();point=text.find(decimal)
        candidates=[i for i in range(min(position,len(text))) if text[i].isdigit()]
        if not candidates:return
        index=candidates[-1]
        if point>=0:
            power=point-index-1 if index<point else point-index
        else:power=sum(c.isdigit() for c in text[index+1:])
        self.interpretText()
        increment=10**power
        value=self.value()+steps*increment
        if isinstance(self,W.QSpinBox):value=int(round(value))
        self.setValue(value)
        text=editor.text();point=text.find(decimal)
        digits=[i for i,c in enumerate(text) if c.isdigit()]
        if point>=0:
            target=point-power-1 if power>=0 else point-power
        else:
            target=digits[-1-power] if 0<=power<len(digits) else (digits[0] if digits else 0)
        editor.setCursorPosition(max(0,min(len(text),target+1)))

class DigitSpinBox(DigitWheel,W.QSpinBox):pass
class DigitDoubleSpinBox(DigitWheel,W.QDoubleSpinBox):pass
