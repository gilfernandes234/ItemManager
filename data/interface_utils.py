from PyQt6.QtWidgets import QWidget, QCheckBox, QHBoxLayout, QVBoxLayout, QLabel, QAbstractButton, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtProperty, QRect, QPoint, QEasingCurve, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient

class ToggleSwitch(QAbstractButton):
    stateChanged = pyqtSignal(bool)

    def __init__(self, parent=None, track_radius=10, thumb_radius=8):
        super().__init__(parent=parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._track_radius = track_radius
        self._thumb_radius = thumb_radius
        self._margin = max(0, self._track_radius - self._thumb_radius)
        self._base_offset = max(self._thumb_radius, self._track_radius)
        self._end_offset = 2 * (self._track_radius if self._track_radius > self._thumb_radius else self._thumb_radius) + 20 # width factor

        self._thumb_pos = self._base_offset 
        self._thumb_color = QColor(255, 255, 255)
        
        # Animations
        self._anim = QPropertyAnimation(self, b"thumb_pos", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.toggled.connect(self._start_anim)

    @pyqtProperty(float)
    def thumb_pos(self):
        return self._thumb_pos

    @thumb_pos.setter
    def thumb_pos(self, pos):
        self._thumb_pos = pos
        self.update()

    def _start_anim(self, checked):
        end = self.width() - self._base_offset if checked else self._base_offset
        self._anim.setStartValue(self._thumb_pos)
        self._anim.setEndValue(end)
        self._anim.start()
        self.stateChanged.emit(checked)

    def sizeHint(self):
        return QSize(44, 24)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track
        track_opacity = 1.0
        if self.isChecked():
            gradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0, QColor("#4a90e2"))
            gradient.setColorAt(1, QColor("#5b9bd5"))
            brush = QBrush(gradient)
        else:
            brush = QBrush(QColor("#32323c")) # Dark gray

        p.setBrush(brush)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)

        # Thumb
        p.setBrush(QBrush(self._thumb_color))
        # thumb_pos acts as center x
        p.drawEllipse(QPoint(int(self._thumb_pos), int(self.height() / 2)), self._thumb_radius, self._thumb_radius)

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

class ModernLabel(QWidget):
    def __init__(self, text, is_header=False):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl = QLabel(text)
        if is_header:
            self.lbl.setObjectName("sectionHeader")
        else:
            self.lbl.setObjectName("propertyLabel")
            
        layout.addWidget(self.lbl)
