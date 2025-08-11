# account_bubble_widget.py

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSpacerItem, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt
import qtawesome as qta

class AccountBubbleWidget(QFrame):
    """
    Sebuah widget kustom berbentuk kartu (bubble) untuk menampilkan
    detail dan aksi dari satu akun trading.
    """
    # Sinyal kustom yang akan dikirim ke parent (AccountManager)
    launch_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    kill_requested = pyqtSignal(str)

    def __init__(self, account_number: str, account_info: dict, parent=None):
        super().__init__(parent)
        self.account_number = account_number
        self.account_info = account_info

        self.setObjectName("AccountBubble")
        self.setMinimumHeight(80)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(20)

        # --- Kolom 1: Info Akun ---
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        self.lbl_account_number = QLabel(self.account_number)
        self.lbl_account_number.setObjectName("BubbleAccountNumber")
        
        server_text = self.account_info.get('server', 'N/A')
        self.lbl_server = QLabel(f"Server: {server_text}")
        self.lbl_server.setObjectName("BubbleSubText")
        
        info_layout.addWidget(self.lbl_account_number)
        info_layout.addWidget(self.lbl_server)
        main_layout.addLayout(info_layout, 2)

        self.lbl_status = QLabel("OFFLINE")
        self.lbl_status.setObjectName("BubbleStatusPill")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_status, 1)

        main_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # --- Kolom 3: Tombol Aksi ---
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        
        self.btn_launch = QPushButton(qta.icon('fa5s.rocket', color='#FFFFFF'), "")
        self.btn_launch.setToolTip(self.tr("Launch Control Panel"))
        self.btn_edit = QPushButton(qta.icon('fa5s.edit', color='#FFFFFF'), "")
        self.btn_edit.setToolTip(self.tr("Edit Account"))
        self.btn_delete = QPushButton(qta.icon('fa5s.trash-alt', color='#FFFFFF'), "")
        self.btn_delete.setToolTip(self.tr("Delete Account"))

        self.btn_kill = QPushButton(qta.icon('fa5s.skull-crossbones', color='#FFFFFF'), "")
        self.btn_kill.setToolTip(self.tr("Force Kill Process"))
        self.btn_kill.setObjectName("BubbleActionButton_Kill")

        action_buttons = [self.btn_launch, self.btn_edit, self.btn_delete, self.btn_kill]
        for btn in action_buttons:
            btn.setObjectName("BubbleActionButton")
            btn.setFixedSize(32, 32)
            actions_layout.addWidget(btn)

        self.btn_kill.setProperty("class", "kill")
        
        main_layout.addLayout(actions_layout, 0) # Stretch factor 0

        # --- Hubungkan Sinyal ---
        self.btn_launch.clicked.connect(lambda: self.launch_requested.emit(self.account_number))
        self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.account_number))
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.account_number))
        self.btn_kill.clicked.connect(lambda: self.kill_requested.emit(self.account_number))
        self.update_status("OFFLINE")

    def update_status(self, status: str):
        status_lower = status.lower()
        if status_lower in ["unresponsive", "crashed"]:
            self.btn_kill.show()
        else:
            self.btn_kill.hide()

        self.lbl_status.setText(status.upper())
        self.lbl_status.setProperty("status", status.lower())
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)