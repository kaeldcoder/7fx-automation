# FILE 3 # D:\7FX Automation\robots\HFT explosive m1\add_account_dialog.py

import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, QMessageBox, QApplication,
                             QLineEdit, QPushButton, QComboBox, QDialogButtonBox, QCheckBox, 
                             QHBoxLayout, QProgressDialog)
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import QMessageBox
from Library.utils.path_finder import (load_known_paths, save_known_paths, 
                                       scan_for_metatrader_enhanced, find_by_smart_search, 
                                       DeepScanner)
from custom_dialogs import StyledDialog
from custom_dialogs import ConfirmationDialog, InfoDialog
from custom_dialogs import CustomProgressDialog

class AddAccountDialog(StyledDialog):
    def __init__(self, robot_root_path: str, known_paths: set, parent=None):
        super().__init__(title=self.tr("Add New Account"), parent=parent)
        self.robot_root_path = robot_root_path
        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)
        self.setMinimumWidth(500)
        self.setMinimumHeight(330)

        # Input fields
        self.acc_num_input = QLineEdit()
        self.acc_num_input.setPlaceholderText(self.tr("Example: 11007xxxx"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText(self.tr("Enter trading password"))
        self.server_input = QLineEdit()
        path_layout = QHBoxLayout()
        self.path_dropdown = QComboBox()
        self.btn_scan = QPushButton(self.tr("Scan"))
        self.btn_scan.setObjectName("ScanButton")
        path_layout.addWidget(self.path_dropdown, 1)
        path_layout.addWidget(self.btn_scan)
        self.save_pass_checkbox = QCheckBox(self.tr("Save Password"))
        self.save_pass_checkbox.setChecked(True)


        # Tambahkan widget ke layout form
        form_layout.addWidget(QLabel(self.tr("Account Number")), 0, 0)
        form_layout.addWidget(self.acc_num_input, 0, 1)
        form_layout.addWidget(QLabel(self.tr("Password")), 1, 0)
        form_layout.addWidget(self.password_input, 1, 1)
        form_layout.addWidget(QLabel(self.tr("Server")), 2, 0)
        form_layout.addWidget(self.server_input, 2, 1)
        form_layout.addWidget(QLabel(self.tr("MT5 Path")), 3, 0)
        form_layout.addLayout(path_layout, 3, 1)
        form_layout.addWidget(self.save_pass_checkbox, 4, 1)

        self.populate_path_dropdown(known_paths)
        self.btn_scan.clicked.connect(self.scan_for_paths)
        self.content_layout.addLayout(form_layout)

        # Tombol OK dan Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setObjectName("DialogButton")
        btn_ok.setProperty("class", "affirmative") # Properti untuk tombol utama

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

        # Atribut untuk thread deep scan
        self.deep_scan_thread = None
        self.deep_scanner = None

    def get_new_account_info(self):
        if not all([self.acc_num_input.text(), self.password_input.text(), self.server_input.text()]):
            return None
        return {
            'number': self.acc_num_input.text(),
            'password': self.password_input.text(),
            'server': self.server_input.text(),
            'path': self.path_dropdown.currentData(),
            'save_password': self.save_pass_checkbox.isChecked()
        }
    def populate_path_dropdown(self, paths: set):
        self.path_dropdown.clear()
        if not paths:
            self.path_dropdown.addItem(self.tr("No MT5 paths found"))
            self.path_dropdown.setEnabled(False)
        else:
            self.path_dropdown.setEnabled(True)
            display_paths = {os.path.basename(os.path.dirname(p)): p for p in paths}
            for display_name, full_path in sorted(display_paths.items()):
                self.path_dropdown.addItem(display_name, userData=full_path)
            

    def scan_for_paths(self):
        current_paths = load_known_paths(self.robot_root_path)
        paths_from_scan = scan_for_metatrader_enhanced() | find_by_smart_search()
        newly_found_paths = current_paths.union(paths_from_scan)

        if len(newly_found_paths) > len(current_paths):
            print(self.tr("New paths found! Updating list."))
            save_known_paths(self.robot_root_path, newly_found_paths)
            self.populate_path_dropdown(newly_found_paths)
            QMessageBox.information(self, self.tr("Quick Scan Finished"), self.tr("{0} new paths found!").format(len(newly_found_paths) - len(current_paths)))
        else:
            print(self.tr("No new paths found from Quick Scan."))
            dialog = ConfirmationDialog(
                title=self.tr("Quick Scan Finished"),
                message=self.tr("No new paths found.\nContinue with DEEP SCAN? (this process can be very slow)"),
                parent=self
            )
            if dialog.exec(): # .exec() akan return True jika "Yes" ditekan
                self.perform_deep_scan()

    def perform_deep_scan(self):
        """Menjalankan Deep Scan di thread terpisah dengan dialog progres."""
        # 1. Setup Thread dan Worker
        self.deep_scan_thread = QThread()
        self.deep_scanner = DeepScanner()
        self.deep_scanner.moveToThread(self.deep_scan_thread)

        # 2. Setup Progress Dialog
        self.progress_dialog = CustomProgressDialog(
            title=self.tr("Deep Scan in Progress"),
            cancel_text=self.tr("Cancel"),
            parent=self
        )
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setFixedWidth(550)
        parent_geometry = self.geometry()
        # Ambil ukuran dialog progres
        dialog_size = self.progress_dialog.sizeHint()
        new_x = parent_geometry.x() + (parent_geometry.width() - dialog_size.width()) // 2
        new_y = parent_geometry.y() + (parent_geometry.height() - dialog_size.height()) // 2

        # Pindahkan dialog ke posisi yang sudah dihitung
        self.progress_dialog.move(new_x, new_y)
        self.progress_dialog.show()

        def update_scan_label(path: str):
            display_path = path if len(path) < 65 else f"...{path[-60:]}"
            self.progress_dialog.setLabelText(self.tr("Scanning:\n{0}").format(display_path))

        self.deep_scanner.directory_changed.connect(update_scan_label)
        # Tangani hasil saat scan selesai
        self.deep_scanner.scan_finished.connect(self.on_deep_scan_finished)
        # Batalkan scan jika pengguna menekan tombol "Batal"
        self.progress_dialog.btn_cancel.clicked.connect(self.deep_scanner.stop)
        # Jalankan worker saat thread dimulai
        self.deep_scan_thread.started.connect(self.deep_scanner.run)
        # Bersihkan thread setelah selesai
        self.deep_scan_thread.finished.connect(self.deep_scan_thread.deleteLater)

        # 4. Mulai Scan
        self.deep_scan_thread.start()

    # --- [FUNGSI BARU] untuk menangani hasil Deep Scan ---
    def on_deep_scan_finished(self, found_paths: set):
        self.progress_dialog.close() # Tutup dialog progres

        current_paths = load_known_paths(self.robot_root_path)
        all_paths = current_paths.union(found_paths)

        if len(all_paths) > len(current_paths):
            new_count = len(all_paths) - len(current_paths)
            message = self.tr("Found {0} new paths!").format(new_count)
            save_known_paths(self.robot_root_path, all_paths)
            self.populate_path_dropdown(all_paths)
        else:
            message = self.tr("No new installations were found.")
        info_dialog = InfoDialog(self.tr("Deep Scan Finished"), message, self)
        info_dialog.exec()
        
        # Hentikan thread dengan benar
        if self.deep_scan_thread and self.deep_scan_thread.isRunning():
            self.deep_scan_thread.quit()
            self.deep_scan_thread.wait()