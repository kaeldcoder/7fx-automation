# FILE 5 # D:\7FX Automation\robots\HFT explosive m1\add_account_dialog.py

import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QDialogButtonBox, QHBoxLayout)
from custom_dialogs import StyledDialog

class EditAccountDialog(StyledDialog):
    def __init__(self, account_info: dict, all_paths: list, parent=None):
        super().__init__(title=self.tr("Edit Account Details"), parent=parent)
        self.account_info = account_info
        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)
        self.setMinimumWidth(350)
        self.setMinimumHeight(230)

        # Input fields
        self.acc_num_input = QLineEdit(account_info.get('number'))
        self.acc_num_input.setReadOnly(True) # Nomor akun tidak bisa diubah

        self.server_input = QLineEdit(account_info.get('server'))
        
        self.path_dropdown = QComboBox()
        # Isi dropdown dengan semua path yang tersedia
        for path in all_paths:
            # Tampilkan nama foldernya saja agar mudah dibaca
            display_name = os.path.basename(os.path.dirname(path))
            self.path_dropdown.addItem(display_name, userData=path) # Simpan path lengkap di userData

        # Pilih path yang saat ini digunakan oleh akun
        current_path = account_info.get('path')
        if current_path:
            index = self.path_dropdown.findData(current_path)
            if index != -1:
                self.path_dropdown.setCurrentIndex(index)
        
        self.content_layout.addLayout(form_layout)

        # Tambahkan widget ke layout form
        form_layout.addWidget(QLabel(self.tr("Account Number")), 0, 0)
        form_layout.addWidget(self.acc_num_input, 0, 1)
        form_layout.addWidget(QLabel(self.tr("Server")), 1, 0)
        form_layout.addWidget(self.server_input, 1, 1)
        form_layout.addWidget(QLabel(self.tr("MT5 Path")), 2, 0)
        form_layout.addWidget(self.path_dropdown, 2, 1)
        

        # Tombol OK dan Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setObjectName("DialogButton")
        btn_ok.setProperty("class", "affirmative")

        btn_cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setObjectName("DialogButton")

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.content_layout.addSpacing(15)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        button_layout.addStretch()
        self.content_layout.addLayout(button_layout)

    def get_updated_info(self):
        """Mengembalikan data yang sudah diperbarui."""
        self.account_info['server'] = self.server_input.text()
        # Ambil path lengkap dari userData dropdown yang dipilih
        self.account_info['path'] = self.path_dropdown.currentData()
        return self.account_info