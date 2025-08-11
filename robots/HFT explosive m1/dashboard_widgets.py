# dashboard_widgets.py

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout # <-- Impor QGridLayout
from PyQt6.QtCore import Qt
import qtawesome as qta
from circular_progress import CircularProgressBar

class KPICard(QFrame):
    """Sebuah widget kartu yang bisa digunakan kembali untuk menampilkan KPI."""
    def __init__(self, icon_name: str, title: str, initial_value="-" * 5):
        super().__init__()
        self.setObjectName("KPICard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(qta.icon(icon_name, color="#ffffff").pixmap(32, 32))
        self.icon_label.setFixedSize(32, 32)
        
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        
        self.title_label = QLabel(title)
        self.title_label.setObjectName("KPITitle")
        
        self.value_label = QLabel(initial_value)
        self.value_label.setObjectName("KPIValue")
        
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.value_label)
        
        layout.addWidget(self.icon_label)
        layout.addLayout(text_layout)

    def set_value(self, value: str):
        self.value_label.setText(value)
        
    def set_value_color(self, color: str):
        self.value_label.setStyleSheet(f"color: {color};")


class KPIPanel(QWidget):
    """Widget yang berisi beberapa KPICard secara horizontal."""
    def __init__(self):
        super().__init__()
        
        # [DIUBAH] Gunakan QGridLayout untuk kontrol ukuran yang presisi
        self.main_layout = QGridLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setHorizontalSpacing(30) # Atur jarak antar kolom grid

        # Buat 4 kartu KPI
        self.kpi_pnl = KPICard("fa5s.dollar-sign", self.tr("TOTAL P/L"))
        self.kpi_pf = KPICard("fa5s.chart-line", self.tr("PROFIT FACTOR"))
        self.kpi_winrate = KPICard("fa5s.bullseye", self.tr("WIN RATE"))
        self.kpi_active_bots = KPICard("fa5s.robot", self.tr("ACTIVE BOTS"))
        
        # [DIUBAH] Tambahkan widget ke grid pada baris 0, di kolom 0 s/d 3
        self.main_layout.addWidget(self.kpi_pnl, 0, 0)
        self.main_layout.addWidget(self.kpi_pf, 0, 1)
        self.main_layout.addWidget(self.kpi_winrate, 0, 2)
        self.main_layout.addWidget(self.kpi_active_bots, 0, 3)