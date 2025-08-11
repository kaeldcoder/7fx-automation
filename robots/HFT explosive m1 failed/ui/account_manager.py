# account_manager.py

import sys
import os
import keyring
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox)
from PyQt6.QtCore import pyqtSignal, Qt
import qtawesome as qta

from ui.dialogs.edit_account_dialog import EditAccountDialog
from ui.dialogs.add_account_dialog import AddAccountDialog
from Library.utils.path_finder import load_accounts_data, save_accounts_data, load_known_paths

# Impor fungsi yang kita butuhkan untuk memuat data
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)
from Library.utils.path_finder import load_accounts_data, save_accounts_data, load_known_paths

class AccountManager(QWidget):
    launch_panel_requested = pyqtSignal(dict)
    def __init__(self, robot_root_path: str, parent=None):
        super().__init__(parent)
        self.robot_root_path = robot_root_path
        # Layout utama
        layout = QVBoxLayout(self)
        
        # 1. Toolbar untuk tombol-tombol aksi
        toolbar_layout = QHBoxLayout()
        self.btn_add = QPushButton(qta.icon('fa5s.plus'), " Tambah Akun")
        self.btn_edit = QPushButton(qta.icon('fa5s.edit'), " Ubah Akun")
        self.btn_delete = QPushButton(qta.icon('fa5s.trash-alt'), " Hapus Akun")
        self.btn_launch = QPushButton(qta.icon('fa5s.rocket'), " Buka Panel Kontrol")
        
        toolbar_layout.addWidget(self.btn_add)
        toolbar_layout.addWidget(self.btn_edit)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_launch)
        layout.addLayout(toolbar_layout)

        # 2. Tabel untuk menampilkan daftar akun
        self.account_table = QTableWidget()
        self.account_table.setColumnCount(4)
        self.account_table.setHorizontalHeaderLabels(["Nomor Akun", "Server", "Nama MT5", "Status"])
        self.account_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.account_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.account_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.account_table.verticalHeader().setVisible(False)
        header = self.account_table.horizontalHeader()
        # [DIUBAH] Atur kolom agar sesuai konten, kecuali kolom "Nama MT5" yang akan melebar
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch) # Nomor Akun
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Server
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)          # Nama MT5
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Custom)
        layout.addWidget(self.account_table)
        
        # Muat data akun ke dalam tabel
        self.load_account_data()
        
        # Hubungkan sinyal tombol ke fungsi (placeholder)
        self.btn_launch.clicked.connect(self.request_launch_control_panel)
        self.btn_edit.clicked.connect(self.edit_selected_account)
        self.btn_delete.clicked.connect(self.delete_selected_account)
        # Sinyal lain akan kita hubungkan nanti
        self.btn_add.clicked.connect(self.add_new_account)

    def add_new_account(self):
        all_paths = load_known_paths(self.robot_root_path)
        if not all_paths:
            QMessageBox.critical(self, "Error", "Tidak ada path MT5 yang ditemukan. Harap lakukan Scan terlebih dahulu dari halaman utama.")
            return

        dialog = AddAccountDialog(self)

        if dialog.exec():
            new_info = dialog.get_new_account_info()
            if not new_info:
                QMessageBox.warning(self, "Input Tidak Lengkap", "Semua field harus diisi.")
                return

            account_number = new_info['number']

            all_accounts_data = load_accounts_data()

            if account_number in all_accounts_data:
                QMessageBox.warning(self, "Gagal", f"Akun {account_number} sudah terdaftar.")
                return

            # Simpan data baru ke dictionary utama
            all_accounts_data[account_number] = {
                'server': new_info['server'],
                'path': new_info['path']
            }
            save_accounts_data(all_accounts_data)

            # Simpan password jika dicentang
            if new_info['save_password']:
                try:
                    keyring.set_password("7FX_HFT_Bot", account_number, new_info['password'])
                except Exception as e:
                    QMessageBox.critical(self, "Gagal Simpan Password", f"Gagal menyimpan password ke Keyring: {e}")

            print(f"Akun baru {account_number} berhasil ditambahkan.")
            # Muat ulang data di tabel untuk menampilkan akun baru
            self.load_account_data()

    def load_account_data(self):
        """Memuat data dari file JSON dan menampilkannya di tabel."""
        self.account_table.setRowCount(0) # Kosongkan tabel dulu
        
        accounts = load_accounts_data(self.robot_root_path)
        paths = load_known_paths(self.robot_root_path)
        
        # Untuk sementara, kita asumsikan setiap akun bisa menggunakan path pertama yang ada
        # Nanti di form "Tambah Akun" kita akan buat lebih spesifik
        default_path = list(paths)[0] if paths else "N/A"

        for acc_num, acc_info in accounts.items():
            row_position = self.account_table.rowCount()
            self.account_table.insertRow(row_position)
            
            # Buat item untuk setiap sel
            item_num = QTableWidgetItem(acc_num)
            item_server = QTableWidgetItem(acc_info.get('server', 'N/A'))
            # Path bisa kita ambil dari info akun jika ada, jika tidak pakai default
            full_path = acc_info.get('path', default_path)
            # Ambil nama folder dari path (misal: C:\...OANDA\terminal64.exe -> OANDA)
            mt5_name = os.path.basename(os.path.dirname(full_path))
            item_path = QTableWidgetItem(mt5_name)
            item_path.setData(Qt.ItemDataRole.UserRole, full_path)
            item_status = QTableWidgetItem("Offline")
            item_status.setIcon(qta.icon('fa5s.power-off', color='red'))
            
            # Masukkan item ke tabel
            self.account_table.setItem(row_position, 0, item_num)
            self.account_table.setItem(row_position, 1, item_server)
            self.account_table.setItem(row_position, 2, item_path)
            self.account_table.setItem(row_position, 3, item_status)

    def edit_selected_account(self):
        selected_rows = self.account_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Peringatan", "Pilih salah satu akun dari tabel untuk diubah.")
            return

        selected_row = selected_rows[0].row()

        # Kumpulkan data akun yang ada dari tabel
        account_number = self.account_table.item(selected_row, 0).text()

        # Kita perlu path lengkap, bukan hanya nama folder. Jadi kita muat ulang.
        all_accounts_data = load_accounts_data(self.robot_root_path)
        all_paths = load_known_paths(self.robot_root_path)

        current_account_info = all_accounts_data.get(account_number, {})
        current_account_info['number'] = account_number
        # Jika path belum tersimpan, coba tebak dari path pertama yang ada
        if 'path' not in current_account_info:
            current_account_info['path'] = list(all_paths)[0] if all_paths else ""

        # Buka dialog edit
        dialog = EditAccountDialog(current_account_info, list(all_paths), self)

        # Jika pengguna menekan "OK"
        if dialog.exec():
            updated_info = dialog.get_updated_info()

            # Update data utama dan simpan ke file
            all_accounts_data[account_number] = {
                'server': updated_info.get('server'),
                'path': updated_info.get('path') # <-- Sekarang path ikut tersimpan!
            }
            save_accounts_data(all_accounts_data)

            # Muat ulang data di tabel untuk menampilkan perubahan
            self.load_account_data()
            print(f"Akun {account_number} berhasil diperbarui.")

    def delete_selected_account(self):
        """Menghapus akun yang dipilih dari tabel dan file data."""
        selected_rows = self.account_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Peringatan", "Pilih salah satu akun dari tabel untuk dihapus.")
            return

        selected_row = selected_rows[0].row()
        account_number = self.account_table.item(selected_row, 0).text()

        # Minta konfirmasi dari pengguna
        reply = QMessageBox.question(self, 'Konfirmasi Hapus',
                                    f"Anda yakin ingin menghapus akun {account_number} secara permanen?\n"
                                    "Tindakan ini tidak bisa dibatalkan.",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Muat data akun yang ada
            all_accounts_data = load_accounts_data(self.robot_root_path)

            # Hapus akun jika ada
            if account_number in all_accounts_data:
                del all_accounts_data[account_number]

                # Simpan kembali data yang sudah diperbarui
                save_accounts_data(all_accounts_data)
                
                # Hapus juga password dari Keyring jika ada
                try:
                    import keyring
                    keyring.delete_password("7FX_HFT_Bot", account_number)
                except (ImportError, keyring.errors.PasswordDeleteError):
                    # Abaikan jika keyring tidak ada atau password tidak ditemukan
                    pass

                print(f"Akun {account_number} berhasil dihapus.")
                
                # Muat ulang data di tabel untuk menampilkan perubahan
                self.load_account_data()
            else:
                QMessageBox.critical(self, "Error", f"Akun {account_number} tidak ditemukan di file data.")

    def request_launch_control_panel(self):
        selected_rows = self.account_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Peringatan", "Pilih salah satu akun dari tabel terlebih dahulu.")
            return
            
        selected_row = selected_rows[0].row()
        
        # Kumpulkan semua data akun dari tabel ke dalam dictionary
        account_info = {
            'number': self.account_table.item(selected_row, 0).text(),
            'server': self.account_table.item(selected_row, 1).text(),
            'path': self.account_table.item(selected_row, 2).data(Qt.ItemDataRole.UserRole),
        }
        
        # Kirim sinyal beserta data akun
        self.launch_panel_requested.emit(account_info)

    # [BARU] Fungsi untuk mengubah status di tabel (misal: dari 'Offline' ke 'Running')
    def update_account_status(self, account_number, status: str):
        """Fungsi untuk mengubah status di tabel (misal: 'OFFLINE', 'RUNNING', 'COOLDOWN')."""
        for row in range(self.account_table.rowCount()):
            if self.account_table.item(row, 0).text() == str(account_number):
                
                if status == "RUNNING":
                    status_item = QTableWidgetItem("Running")
                    status_item.setIcon(qta.icon('fa5s.robot', color='green'))
                elif status == "COOLDOWN":
                    status_item = QTableWidgetItem("Cooldown")
                    status_item.setIcon(qta.icon('fa5s.hourglass-half', color='#E67E22')) # Warna oranye
                else: # Status "STOPPED" atau lainnya
                    status_item = QTableWidgetItem("Offline")
                    status_item.setIcon(qta.icon('fa5s.power-off', color='red'))
                
                self.account_table.setItem(row, 3, status_item)
                break

# Blok untuk testing mandiri
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = AccountManager()
    window.setWindowTitle("Test Account Manager")
    window.resize(800, 400)
    window.show()
    sys.exit(app.exec())