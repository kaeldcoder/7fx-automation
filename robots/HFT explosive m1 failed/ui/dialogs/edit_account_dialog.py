import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QDialogButtonBox)

class EditAccountDialog(QDialog):
    def __init__(self, account_info: dict, all_paths: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ubah Detail Akun")

        # Simpan data yang akan diedit
        self.account_info = account_info
        
        # Layout utama
        layout = QVBoxLayout(self)
        form_layout = QGridLayout()

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

        # Tambahkan widget ke layout form
        form_layout.addWidget(QLabel("Nomor Akun:"), 0, 0)
        form_layout.addWidget(self.acc_num_input, 0, 1)
        form_layout.addWidget(QLabel("Server:"), 1, 0)
        form_layout.addWidget(self.server_input, 1, 1)
        form_layout.addWidget(QLabel("Path MT5:"), 2, 0)
        form_layout.addWidget(self.path_dropdown, 2, 1)
        
        layout.addLayout(form_layout)

        # Tombol OK dan Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_updated_info(self):
        """Mengembalikan data yang sudah diperbarui."""
        self.account_info['server'] = self.server_input.text()
        # Ambil path lengkap dari userData dropdown yang dipilih
        self.account_info['path'] = self.path_dropdown.currentData()
        return self.account_info