import os
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import COLORS


def _asset_path(relative_path):
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parents[2]
    return str(base_path / relative_path)


def apply_shadow(widget, blur=36, y_offset=12, alpha=90):
    shadow_color = QColor(COLORS["shadow"])
    shadow_color.setAlpha(alpha)
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    shadow.setColor(shadow_color)
    widget.setGraphicsEffect(shadow)


class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WindowRoot")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor(COLORS["window_bg"]))
        base.setColorAt(0.45, QColor(COLORS["window_mid"]))
        base.setColorAt(1.0, QColor(COLORS["window_end"]))
        painter.fillRect(rect, base)

        painter.setPen(Qt.NoPen)

        glow_a_color = QColor(COLORS["backdrop_glow_primary"])
        glow_a_color.setAlpha(COLORS["backdrop_glow_primary_alpha"])
        glow_a = QLinearGradient(0, rect.height() * 0.70, rect.width() * 0.35, rect.height())
        glow_a.setColorAt(0.0, glow_a_color)
        glow_a.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_a)
        painter.drawRoundedRect(-120, rect.height() - 280, rect.width() * 0.55, 360, 80, 80)

        glow_b_color = QColor(COLORS["backdrop_glow_secondary"])
        glow_b_color.setAlpha(COLORS["backdrop_glow_secondary_alpha"])
        glow_b = QLinearGradient(rect.width() * 0.55, 0, rect.width(), rect.height() * 0.50)
        glow_b.setColorAt(0.0, glow_b_color)
        glow_b.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_b)
        painter.drawRoundedRect(rect.width() * 0.62, -60, rect.width() * 0.45, rect.height() * 0.48, 100, 100)

        line_color = QColor(COLORS["backdrop_line"])
        line_color.setAlpha(COLORS["backdrop_line_alpha"])
        line_pen = QPen(line_color, 1.1)
        painter.setPen(line_pen)
        painter.drawLine(0, rect.height() * 0.24, rect.width() * 0.47, 0)
        painter.drawLine(rect.width() * 0.76, 0, rect.width(), rect.height() * 0.18)
        painter.drawLine(rect.width() * 0.70, rect.height() * 0.62, rect.width(), rect.height() * 0.40)

        arc_color = QColor(COLORS["backdrop_arc"])
        arc_color.setAlpha(COLORS["backdrop_arc_alpha"])
        painter.setPen(QPen(arc_color, 14))
        painter.drawArc(-160, rect.height() - 320, 520, 380, 0, 64 * 120)

        path_color = QColor(COLORS["backdrop_path"])
        path_color.setAlpha(COLORS["backdrop_path_alpha"])
        painter.setPen(QPen(path_color, 4))
        path = QPainterPath()
        path.moveTo(rect.width() * 0.55, rect.height() * 0.40)
        path.cubicTo(
            rect.width() * 0.66,
            rect.height() * 0.34,
            rect.width() * 0.80,
            rect.height() * 0.40,
            rect.width() * 0.91,
            rect.height() * 0.32,
        )
        painter.drawPath(path)


class BrandMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 42)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        outer = QPolygonF(
            [
                QPointF(4, 36),
                QPointF(21, 5),
                QPointF(38, 36),
            ]
        )
        grad = QLinearGradient(4, 6, 38, 36)
        grad.setColorAt(0.0, QColor(COLORS["accent_strong"]))
        grad.setColorAt(1.0, QColor(COLORS["accent_deep"]))
        painter.setBrush(grad)
        painter.drawPolygon(outer)

        cut = QPainterPath()
        cut.moveTo(15, 30)
        cut.lineTo(21, 18)
        cut.lineTo(27, 30)
        cut.closeSubpath()
        painter.setBrush(QColor(COLORS["brand_cutout"]))
        painter.drawPath(cut)

        leaf = QPainterPath()
        leaf.moveTo(25, 26)
        leaf.cubicTo(33, 21, 35, 27, 31, 32)
        leaf.cubicTo(27, 36, 22, 33, 25, 26)
        painter.setBrush(QColor(COLORS["brand_leaf"]))
        painter.drawPath(leaf)


class BrandLogo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo_path = _asset_path("dados/logo.svg")
        if os.path.exists(logo_path):
            logo = QSvgWidget(logo_path)
            logo.setFixedSize(48, 48)
            layout.addWidget(logo, 0, Qt.AlignCenter)
            self._logo_widget = logo
        else:
            fallback = BrandMark()
            layout.addWidget(fallback, 0, Qt.AlignCenter)
            self._logo_widget = fallback


class UserChip(QFrame):
    def __init__(self, name="Gleidson", badge="3", parent=None):
        super().__init__(parent)
        self.setObjectName("UserChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        avatar = QLabel(name[:1].upper())
        avatar.setObjectName("UserAvatar")

        label = QLabel(name)
        label.setObjectName("UserName")

        badge_label = QLabel(str(badge))
        badge_label.setObjectName("UserBadge")

        layout.addWidget(avatar)
        layout.addWidget(label)
        layout.addWidget(badge_label)


class MetricItem(QFrame):
    def __init__(self, icon_text, value, label, accent=False, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricItem")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(12)

        icon = QLabel(icon_text)
        icon.setObjectName("MetricIcon")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("MetricValuePrimary" if accent else "MetricValue")

        self.text_label = QLabel(label)
        self.text_label.setObjectName("MetricLabel")

        text_col.addWidget(self.value_label)
        text_col.addWidget(self.text_label)

        layout.addWidget(icon)
        layout.addLayout(text_col, 1)

    def set_value(self, value):
        self.value_label.setText(str(value))

    def set_label(self, label):
        self.text_label.setText(label)


class ActionTile(QFrame):
    clicked = Signal()

    def __init__(self, icon_text, title, variant="secondary", parent=None):
        super().__init__(parent)
        self._base_name = "ActionPrimary" if variant == "primary" else "ActionSecondary"
        self.setObjectName(self._base_name)
        self.setProperty("hovered", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        icon = QLabel(icon_text)
        icon.setObjectName("ActionIconPrimary" if variant == "primary" else "ActionIconSecondary")

        title_label = QLabel(title)
        title_label.setObjectName("ActionTitle")

        chevron = QLabel("" if variant == "primary" else "›")
        chevron.setObjectName("ActionChevron")

        layout.addWidget(icon)
        layout.addWidget(title_label)
        layout.addStretch(1)
        layout.addWidget(chevron)

        apply_shadow(self, blur=28, y_offset=10, alpha=70 if variant == "primary" else 34)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)
