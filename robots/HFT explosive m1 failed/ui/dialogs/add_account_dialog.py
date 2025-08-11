import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, QMessageBox, QApplication,
                             QLineEdit, QPushButton, QComboBox, QDialogButtonBox, QCheckBox, QHBoxLayout)
from PyQt6.QtCore import Qt
from Library.utils.path_finder import (load_known_paths, save_known_paths, 
                                       scan_for_metatrader_enhanced, find_by_smart_search, 
                                       find_by_searching_disk)

class AddAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Akun Baru")

        layout = QVBoxLayout(self)
        form_layout = QGridLayout()

        # Input fields
        self.acc_num_input = QLineEdit()
        self.acc_num_input.setPlaceholderText("Contoh: 110070256")
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Masukkan password trading")

        self.server_input = QLineEdit()
        path_layout = QHBoxLayout()
        self.path_dropdown = QComboBox()
        self.btn_scan = QPushButton("Scan")

        path_layout.addWidget(self.path_dropdown, 1) # Dropdown akan memakan sisa ruang
        path_layout.addWidget(self.btn_scan)

        self.save_pass_checkbox = QCheckBox("Simpan Password")
        self.save_pass_checkbox.setChecked(True) # Defaultnya tercentang

        # Tambahkan widget ke layout form
        form_layout.addWidget(QLabel("Nomor Akun:"), 0, 0)
        form_layout.addWidget(self.acc_num_input, 0, 1)
        form_layout.addWidget(QLabel("Password:"), 1, 0)
        form_layout.addWidget(self.password_input, 1, 1)
        form_layout.addWidget(QLabel("Server:"), 2, 0)
        form_layout.addWidget(self.server_input, 2, 1)
        form_layout.addWidget(QLabel("Path MT5:"), 3, 0)
        form_layout.addLayout(path_layout, 3, 1)
        form_layout.addWidget(self.save_pass_checkbox, 4, 1)
        
        layout.addLayout(form_layout)

        self.populate_path_dropdown(load_known_paths())
        self.btn_scan.clicked.connect(self.scan_for_paths)

        # Tombol OK dan Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_new_account_info(self):
        """Mengembalikan data akun baru dari input pengguna."""
        if not all([self.acc_num_input.text(), self.password_input.text(), self.server_input.text()]):
            return None # Kembalikan None jika ada field yang kosong

        return {
            'number': self.acc_num_input.text(),
            'password': self.password_input.text(),
            'server': self.server_input.text(),
            'path': self.path_dropdown.currentData(),
            'save_password': self.save_pass_checkbox.isChecked()
        }
    def populate_path_dropdown(self, paths: set):
        """Mengosongkan dan mengisi ulang dropdown path."""
        self.path_dropdown.clear()
        current_path = self.path_dropdown.currentData() # Simpan pilihan saat ini jika ada
        
        for path in sorted(list(paths)):
            display_name = os.path.basename(os.path.dirname(path))
            self.path_dropdown.addItem(display_name, userData=path)
        
        # Coba pulihkan pilihan sebelumnya
        if current_path:
            index = self.path_dropdown.findData(current_path)
            if index != -1:
                self.path_dropdown.setCurrentIndex(index)

    def scan_for_paths(self):
        """Memulai proses scan dan memperbarui dropdown jika ada path baru."""
        print("Memulai Quick Scan...")
        current_paths = load_known_paths()
        paths_registry = scan_for_metatrader_enhanced()
        paths_smart = find_by_smart_search()
        newly_found_paths = current_paths | paths_registry | paths_smart

        if len(newly_found_paths) > len(current_paths):
            print("Ditemukan path baru! Memperbarui daftar.")
            save_known_paths(newly_found_paths)
            self.populate_path_dropdown(newly_found_paths)
        else:
            print("Tidak ada path baru ditemukan dari Quick Scan.")
            reply = QMessageBox.question(self, 'Scan Cepat Selesai', 
                                        "Tidak ada path baru ditemukan.\nLanjutkan dengan DEEP SCAN? (proses ini lambat)",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                        QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.perform_deep_scan()

    def perform_deep_scan(self):
        """Menjalankan Deep Scan yang lebih menyeluruh."""
        print("Memulai Deep Scan... Harap tunggu.")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor) # Ubah cursor jadi loading
        
        current_paths = load_known_paths()
        paths_deep = find_by_searching_disk()
        newly_found_paths = current_paths | paths_deep
        
        QApplication.restoreOverrideCursor() # Kembalikan cursor normal

        if len(newly_found_paths) > len(current_paths):
            print("Ditemukan path baru dari Deep Scan!")
            save_known_paths(newly_found_paths)
            self.populate_path_dropdown(newly_found_paths)
        else:
            QMessageBox.information(self, "Selesai", "Deep Scan selesai. Tidak ada instalasi baru ditemukan.")