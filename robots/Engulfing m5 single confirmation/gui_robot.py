import sys, winreg, os, json, time
from logic_engulfing import Worker
import qtawesome as qta
import MetaTrader5 as mt5
import ctypes
import keyring
from PyQt6.QtGui import QFontDatabase, QFont, QPixmap, QAction, QIcon, QMovie # <-- BARU
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit, QDoubleSpinBox, 
                             QPushButton, QTextEdit, QComboBox, QMessageBox, QGroupBox, QSplashScreen,
                             QCompleter, QCheckBox)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def save_known_paths(paths):
    with open("known_paths.json", "w") as f:
        json.dump(list(paths), f, indent=4)
def load_known_paths():
    if not os.path.exists("known_paths.json"): return []
    try:
        with open("known_paths.json", "r") as f: return json.load(f)
    except json.JSONDecodeError: return []
def save_accounts_data(data):
    with open("accounts.json", "w") as f:
        json.dump(data, f, indent=4)
def load_accounts_data():
    if not os.path.exists("accounts.json"): return {}
    try:
        with open("accounts.json", "r") as f: return json.load(f)
    except json.JSONDecodeError: return {}
def scan_for_metatrader_enhanced():
    found_paths = set()
    keys_to_check = [(winreg.HKEY_CURRENT_USER, r"Software\MetaQuotes\Terminal"), (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\MetaQuotes\Terminal"), (winreg.HKEY_LOCAL_MACHINE, r"Software\MetaQuotes\Terminal")]
    for hkey, key_path in keys_to_check:
        try:
            main_key = winreg.OpenKey(hkey, key_path, 0, winreg.KEY_READ)
            for i in range(winreg.QueryInfoKey(main_key)[0]):
                sub_key_name = winreg.EnumKey(main_key, i)
                sub_key = winreg.OpenKey(main_key, sub_key_name)
                try:
                    exe_path, _ = winreg.QueryValueEx(sub_key, "ExePath")
                    if exe_path: found_paths.add(exe_path)
                except FileNotFoundError: continue
                finally: winreg.CloseKey(sub_key)
        except FileNotFoundError: continue
        finally:
            if 'main_key' in locals(): winreg.CloseKey(main_key)
    return list(found_paths)
def check_known_paths():
    known_paths = [r"C:\Program Files\OANDA MetaTrader 5\terminal64.exe", r"C:\Program Files\MetaTrader 5\terminal64.exe"]
    found_paths = []
    for path in known_paths:
        if os.path.exists(path): found_paths.append(path)
    return found_paths
def find_by_smart_search():
    found_paths = []
    target_file = "terminal64.exe"
    keywords = ["metatrader", "mt5"]
    base_dirs = [os.environ.get("ProgramFiles", "C:\\Program Files"), os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")]
    for base_dir in base_dirs:
        try:
            for item_name in os.listdir(base_dir):
                item_path = os.path.join(base_dir, item_name)
                if os.path.isdir(item_path):
                    if any(keyword in item_name.lower() for keyword in keywords):
                        potential_path = os.path.join(item_path, target_file)
                        if os.path.exists(potential_path):
                            found_paths.append(potential_path)
        except FileNotFoundError:
            continue
    return found_paths
def find_by_searching_disk():
    found_paths = []
    target_file = "terminal64.exe"
    search_locations = [os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), ""), os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "")]
    if os.path.exists("D:\\"): search_locations.append("D:\\")
    for location in search_locations:
        for root, dirs, files in os.walk(location):
            if target_file in files:
                path = os.path.join(root, target_file)
                found_paths.append(path)
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.lower() in ['windows', 'python', '$recycle.bin']]
    return found_paths

class RobotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Control Panel Robot Trading")
        self.setGeometry(100, 100, 550, 700)
        self._old_pos = None
        self.thread = None
        self.worker = None

        # --- SETUP WIDGET & LAYOUT UTAMA ---
        self.main_container = QWidget()
        self.main_container.setObjectName("MainContainer")
        self.setCentralWidget(self.main_container)
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_container.setLayout(self.main_layout)

        # --- SETUP IKON APLIKASI ---
        icon_path = resource_path("asset/icon/finance_icon.png")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
        else:
            print(f"PERINGATAN: File ikon '{icon_path}' tidak ditemukan.")

        # --- SETUP HEADER ---
        header_widget = QWidget()
        header_widget.setObjectName("Header")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 5, 10, 5)
        header_widget.setLayout(header_layout)
        logo_label = QLabel("🤖")
        logo_label.setFont(QFont("Roboto", 16))
        title_label = QLabel("Engulfing m5 Single Confirmation")
        title_label.setObjectName("HeaderTitle")
        self.btn_minimize = QPushButton(qta.icon('fa5s.window-minimize', color='#ecf0f1'), "")
        self.btn_close = QPushButton(qta.icon('fa5s.times', color='#ecf0f1'), "")
        self.btn_minimize.setObjectName("WindowButton")
        self.btn_close.setObjectName("WindowButton")
        self.btn_minimize.setFixedSize(30, 30)
        self.btn_close.setFixedSize(30, 30)
        self.btn_minimize.clicked.connect(self.showMinimized)
        self.btn_close.clicked.connect(self.close)
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_minimize)
        header_layout.addWidget(self.btn_close)
        self.main_layout.addWidget(header_widget)

        # --- SETUP KONTEN (TABS, LOG, TOMBOL) ---
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.addLayout(content_layout)
        self.tabs = QTabWidget()
        self.tab_kredensial = QWidget()
        self.tab_pengaturan = QWidget()
        self.tabs.addTab(self.tab_kredensial, "Kredensial Akun")
        self.tabs.addTab(self.tab_pengaturan, "Pengaturan Strategi")
        
        # PANGGIL FUNGSI UNTUK MEMBUAT WIDGET DULU
        self.create_credential_tab()
        self.create_settings_tab()
        
        content_layout.addWidget(self.tabs)
        content_layout.addWidget(QLabel("Log Status:"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        content_layout.addWidget(self.log_area)

        self.btn_toggle_engine = QPushButton("") # Teks dikosongkan, kita akan pakai ikon besar
        # self.btn_toggle_engine.setObjectName("StartButton")
        self.btn_toggle_engine.setEnabled(False) 
        self.btn_toggle_engine.setFixedSize(200, 60) # Ukuran dibuat persegi (80x80 piksel)
        self.btn_toggle_engine.setIconSize(QSize(30, 30)) # Ukuran ikon diperbesar
        self.btn_toggle_engine.clicked.connect(self.on_toggle_engine_clicked)
        self.update_toggle_button_ui(is_running=False) 

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.btn_toggle_engine)
        button_layout.addStretch()
        content_layout.addLayout(button_layout)

        self.is_connected = False

        # button_layout = QHBoxLayout()
        # button_layout.addWidget(self.btn_toggle_engine)
        # content_layout.addLayout(button_layout)

        self.accounts_data = load_accounts_data()
        if self.accounts_data:
            self.input_acc_num.addItems(self.accounts_data.keys())
        self.update_dropdown_from_list(load_known_paths())
        if self.path_dropdown.count() > 0:
            self.log_area.setText("Path MT5 yang tersimpan berhasil dimuat.")

    def on_toggle_engine_clicked(self):
        if self.thread and self.thread.isRunning():
            self.stop_robot()
        else:
            self.start_robot()

    def update_toggle_button_ui(self, is_running):
        if is_running:
            self.btn_toggle_engine.setText(" Stop Engine")
            self.btn_toggle_engine.setObjectName("StopButton")
            self.btn_toggle_engine.setIcon(qta.icon('fa5s.stop', color='white'))
        else:
            self.btn_toggle_engine.setText(" Start Engine")
            self.btn_toggle_engine.setObjectName("StartButton")
            self.btn_toggle_engine.setIcon(qta.icon('fa5s.play', color='white'))
        
        self.btn_toggle_engine.style().unpolish(self.btn_toggle_engine)
        self.btn_toggle_engine.style().polish(self.btn_toggle_engine)

        # --- BARU MUAT DATA SETELAH SEMUA WIDGET DIBUAT ---
    def on_connection_toggle_clicked(self):
        """Memeriksa status koneksi dan memutuskan untuk connect atau disconnect."""
        if self.is_connected:
            self.disconnect_from_mt5()
        else:
            self.connect_to_mt5()

    def on_account_selected(self, account_number):
        """Dipanggil saat user memilih atau mengetik nomor akun."""
        if account_number in self.accounts_data:
            data = self.accounts_data[account_number]
            server = data.get("server", "")
            self.input_acc_server.setText(server)
            
            service_name = "7FX_LAUNCHER_ROBOTS"
            password = keyring.get_password(service_name, account_number)

            if password:
                self.input_acc_pass.setText(password)
                self.input_save_pass.setChecked(True)
            else:
                self.input_acc_pass.clear()
                self.input_save_pass.setChecked(False)

    def on_password_changed(self, text):
        """Menampilkan atau menyembunyikan checkbox berdasarkan isi password."""
        if text: # Jika ada teks di kolom password
            self.input_save_pass.show()
        else: # Jika kolom password kosong
            self.input_save_pass.hide()

    def toggle_password_visibility(self):
        """Mengubah visibilitas password dan ikonnya."""
        # Cek mode password saat ini
        if self.input_acc_pass.echoMode() == QLineEdit.EchoMode.Password:
            # Jika sedang tersembunyi, tampilkan
            self.input_acc_pass.setEchoMode(QLineEdit.EchoMode.Normal)
            # Ganti ikon menjadi mata tercoret
            self.show_pass_action.setIcon(qta.icon('fa5s.eye-slash', color='gray'))
        else:
            # Jika sedang terlihat, sembunyikan kembali
            self.input_acc_pass.setEchoMode(QLineEdit.EchoMode.Password)
            # Ganti ikon menjadi mata terbuka
            self.show_pass_action.setIcon(qta.icon('fa5s.eye', color='gray'))

    def connect_to_mt5(self):
        try:
        # --- validasi input dipindah ke dalam try-except ---
            acc_num_str = self.input_acc_num.currentText()
            if not acc_num_str:
                QMessageBox.warning(self, "Input Tidak Lengkap", "Nomor Akun harus diisi.")
                return

            acc_num = int(acc_num_str) # Baris ini bisa menyebabkan error jika bukan angka
            acc_pass = self.input_acc_pass.text()
            acc_server = self.input_acc_server.text()
            mt5_path = self.path_dropdown.currentData()

            if not all([acc_pass, acc_server, mt5_path]):
                QMessageBox.warning(self, "Input Tidak Lengkap", "Harap isi semua detail koneksi.")
                return

        except ValueError:
            QMessageBox.critical(self, "Input Error", "Nomor Akun harus berupa angka.")
            return # Hentikan eksekusi

        # Coba inisialisasi koneksi
        if not mt5.initialize(path=mt5_path, login=acc_num, password=acc_pass, server=acc_server):
            error_code, error_desc = mt5.last_error()
            user_friendly_message = (f"Koneksi Gagal.\n\n"
                                    f"Pesan dari server: {error_desc}\n\n"
                                    f"Silakan periksa kembali Nomor Akun, Password, dan Server Anda.")
            self.log_area.append(f"❌ Koneksi Gagal (Kode: {error_code})")
            QMessageBox.critical(self, "Kredensial Salah atau Gagal Terhubung", user_friendly_message)
            self.is_connected = False
            return

        # Jika berhasil:
        self.is_connected = True
        self.log_area.append("✅ Koneksi Berhasil! Menyimpan data akun...")

        service_name = "7FX_LAUNCHER_ROBOTS" # Nama "grup" untuk kredensial kita
        account_number_str = str(acc_num)

        password_to_save = ""
        if self.input_save_pass.isChecked():
        # SIMPAN password ke brankas Windows, bukan ke file JSON
            keyring.set_password(service_name, account_number_str, acc_pass)
            self.log_area.append("   Password disimpan dengan aman di Credential Manager.")
        else:
            # HAPUS password dari brankas jika user tidak ingin menyimpannya
            try:
                keyring.delete_password(service_name, account_number_str)
                self.log_area.append("   Password yang tersimpan sebelumnya telah dihapus.")
            except keyring.errors.PasswordDeleteError:
                # Tidak apa-apa jika password memang tidak ada untuk dihapus
                pass

        # Update data di memori
        self.accounts_data[acc_num_str] = {
            "server": self.input_acc_server.text()
        }
        
        # Simpan ke file
        save_accounts_data(self.accounts_data)
        
        # Refresh dropdown jika ada nomor akun baru
        if acc_num_str not in [self.input_acc_num.itemText(i) for i in range(self.input_acc_num.count())]:
            self.input_acc_num.addItem(acc_num_str)
        
        # Nonaktifkan inputan agar tidak diubah-ubah
        self.input_acc_num.setEnabled(False)
        self.input_acc_pass.setEnabled(False)
        self.input_acc_server.setEnabled(False)
        self.path_dropdown.setEnabled(False)
        self.btn_scan.setEnabled(False)
        # self.btn_connect.setEnabled(False)

        # Aktifkan tombol Start
        self.btn_toggle_engine.setEnabled(True)

        # Panggil fungsi untuk mengisi daftar simbol
        self.populate_symbols()
        self.update_connection_button_ui()

    def disconnect_from_mt5(self):
        """Memutuskan koneksi MT5 dan mereset UI."""
        # Pastikan bot sedang tidak berjalan
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "Proses Berjalan", "Harap hentikan engine terlebih dahulu sebelum disconnect.")
            return

        mt5.shutdown()
        self.is_connected = False
        self.log_area.append("🔌 Koneksi ke akun telah diputuskan.")

        # Aktifkan kembali semua inputan
        self.input_acc_num.setEnabled(True)
        self.input_acc_pass.setEnabled(True)
        self.input_acc_server.setEnabled(True)
        self.path_dropdown.setEnabled(True)
        self.btn_scan.setEnabled(True)
        
        # Nonaktifkan tombol Start Engine
        self.btn_toggle_engine.setEnabled(False)

        # Kosongkan daftar simbol
        self.input_symbol.clear()

        # Update tampilan tombol Connect/Disconnect
        self.update_connection_button_ui()
    
    def update_connection_button_ui(self):
        """Mengubah tampilan tombol connect/disconnect berdasarkan status."""
        if self.is_connected:
            self.btn_connect.setText("🔌 Disconnect from Account")
            # Kita bisa gunakan style yang sama dengan tombol Stop (merah)
            self.btn_connect.setObjectName("DisconnectButton") 
        else:
            self.btn_connect.setText("🔗 Connect to Account")
            # Beri nama objek baru agar bisa di-style sendiri
            self.btn_connect.setObjectName("ConnectButton") 

        # Terapkan ulang style
        self.btn_connect.style().unpolish(self.btn_connect)
        self.btn_connect.style().polish(self.btn_connect)

    def populate_symbols(self):
        self.log_area.append("Mengambil daftar simbol dari server...")
        try:
            symbols = mt5.symbols_get()
            if symbols:
                # Ambil nama dari setiap simbol
                symbol_names = sorted([s.name for s in symbols])
                self.input_symbol.clear()
                self.input_symbol.addItems(symbol_names)
                self.log_area.append(f"✅ Berhasil memuat {len(symbol_names)} simbol.")
            else:
                self.log_area.append("❌ Gagal mendapatkan daftar simbol.")
        except Exception as e:
            self.log_area.append(f"❌ Error saat mengambil simbol: {e}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._old_pos is not None:
            delta = event.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._old_pos = None

    def create_credential_tab(self):
        layout = QGridLayout()
        
        # Baris 0: Nomor Akun
        layout.addWidget(QLabel("Nomor Akun:"), 0, 0)
        self.input_acc_num = QComboBox()
        self.input_acc_num.setEditable(True)
        self.input_acc_num.currentTextChanged.connect(self.on_account_selected)
        layout.addWidget(self.input_acc_num, 0, 1, 1, 2)

        # Baris 1: Password
        layout.addWidget(QLabel("Password:"), 1, 0)
        self.input_acc_pass = QLineEdit()
        self.input_acc_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_acc_pass.textChanged.connect(self.on_password_changed)
        self.show_pass_icon = qta.icon('fa5s.eye', color='gray')
        self.show_pass_action = QAction(self.show_pass_icon, "Show/Hide Password", self)
        self.show_pass_action.triggered.connect(self.toggle_password_visibility)
        self.input_acc_pass.addAction(self.show_pass_action, QLineEdit.ActionPosition.TrailingPosition)
        layout.addWidget(self.input_acc_pass, 1, 1, 1, 2)

        # --- DIUBAH: Checkbox dipindah ke baris 2 ---
        self.input_save_pass = QCheckBox("Save Password")
        self.input_save_pass.hide()
        
        # Letakkan di baris 2, kolom 1 agar posisinya menjorok ke dalam
        layout.addWidget(self.input_save_pass, 2, 1, 1, 2)

        # Baris 3: Server (sebelumnya di baris 2)
        layout.addWidget(QLabel("Server:"), 3, 0)
        self.input_acc_server = QLineEdit()
        layout.addWidget(self.input_acc_server, 3, 1, 1, 2)
        
        # Baris 4: Path MT5 (sebelumnya di baris 3)
        layout.addWidget(QLabel("Path MT5:"), 4, 0)
        self.path_dropdown = QComboBox()
        layout.addWidget(self.path_dropdown, 4, 1)
        
        self.btn_scan = QPushButton("Scan")
        self.btn_scan.clicked.connect(self.scan_for_new_paths)
        layout.addWidget(self.btn_scan, 4, 2)
        
        # Baris 5: Tombol Connect (sebelumnya di baris 4)
        self.btn_connect = QPushButton("🔗 Connect to Account")
        self.btn_connect.clicked.connect(self.on_connection_toggle_clicked)
        layout.addWidget(self.btn_connect, 5, 0, 1, 3)

        layout.setColumnStretch(1, 4)
        layout.setColumnStretch(2, 1)
        
        self.tab_kredensial.setLayout(layout)
    
    def update_dropdown_from_list(self, paths):
        """Fungsi helper untuk mengisi dropdown dari sebuah list."""
        self.path_dropdown.clear()
        if paths:
            unique_paths = sorted(list(set(paths)))
            for path in unique_paths:
                try:
                    friendly_name = os.path.basename(os.path.dirname(path))
                except:
                    friendly_name = path
                self.path_dropdown.addItem(friendly_name, userData=path)

    def scan_for_new_paths(self):
        """Hanya menjalankan metode scan cepat."""
        self.log_area.setText("Memulai scan cepat (Registry & Smart Search)...")
        QApplication.processEvents()

        paths_registry = scan_for_metatrader_enhanced()
        paths_smart = find_by_smart_search()
        
        current_paths = load_known_paths()
        newly_found_paths = set(current_paths) | set(paths_registry) | set(paths_smart)

        if len(newly_found_paths) > len(current_paths):
            self.log_area.append("✅ Ditemukan path baru! Daftar diperbarui.")
            self.update_dropdown_from_list(list(newly_found_paths))
            save_known_paths(newly_found_paths)
        else:
            self.log_area.append("Tidak ada path baru yang ditemukan dari scan cepat.")
            # --- BARU: Munculkan pop-up konfirmasi ---
            reply = QMessageBox.question(self, 'Scan Cepat Gagal', 
                                         "Tidak ditemukan instalasi baru.\n\nApakah Anda ingin menjalankan DEEP SCAN? (proses ini bisa sangat lambat)",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.perform_deep_scan()

    def perform_deep_scan(self):
        """Fungsi terpisah untuk menjalankan scan lambat."""
        self.log_area.append("Memulai Deep Scan (seluruh disk)... Harap tunggu.")
        QApplication.processEvents()

        paths_deep = find_by_searching_disk()
        
        current_paths = load_known_paths()
        newly_found_paths = set(current_paths) | set(paths_deep)

        if len(newly_found_paths) > len(current_paths):
            self.log_area.append("✅ Ditemukan path baru dari Deep Scan! Daftar diperbarui.")
            self.update_dropdown_from_list(list(newly_found_paths))
            save_known_paths(newly_found_paths)
        else:
            self.log_area.append("Deep Scan selesai. Tidak ada instalasi baru yang ditemukan.")
    
    # ... (Fungsi create_settings_tab, start_robot, stop_robot tetap sama) ...
    def create_settings_tab(self):
        tab_layout = QVBoxLayout()
        group_box = QGroupBox("Parameter Strategi")
        layout = QGridLayout()

        # ... (semua widget diletakkan di dalam 'layout' QGroupBox)
        layout.addWidget(QLabel("Simbol:"), 0, 0)
        self.input_symbol = QComboBox()
        self.input_symbol.setEditable(True) # Agar bisa dicari/diketik
        self.input_symbol.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.input_symbol.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.input_symbol.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        layout.addWidget(self.input_symbol, 0, 1)
        # ... (dan seterusnya untuk Risk, R:R, Magic Number)
        layout.addWidget(QLabel("Resiko (%):"), 1, 0)
        self.input_risk = QDoubleSpinBox()
        self.input_risk.setValue(1.0)
        self.input_risk.setSingleStep(0.1)
        layout.addWidget(self.input_risk, 1, 1)
        layout.addWidget(QLabel("Risk:Reward Ratio:"), 2, 0)
        self.input_rr = QDoubleSpinBox()
        self.input_rr.setValue(3.0)
        self.input_rr.setSingleStep(0.1)
        layout.addWidget(self.input_rr, 2, 1)
        layout.addWidget(QLabel("Magic Number:"), 3, 0)
        self.input_magic = QLineEdit("12345")
        layout.addWidget(self.input_magic, 3, 1)

        group_box.setLayout(layout)
        tab_layout.addWidget(group_box)
        self.tab_pengaturan.setLayout(tab_layout)
    def start_robot(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Belum Terhubung", "Silakan hubungkan ke akun Anda terlebih dahulu.")
            return
        
        # Kumpulkan semua konfigurasi dari GUI
        config = {
            "acc_num": int(self.input_acc_num.currentText()),
            "acc_pass": self.input_acc_pass.text(),
            "acc_server": self.input_acc_server.text(),
            "mt5_path": self.path_dropdown.currentData(),
            "symbol": self.input_symbol.currentText(),
            "risk_percent": self.input_risk.value(),
            "rr_ratio": self.input_rr.value(),
            "magic_number": int(self.input_magic.text())
        }

        self.log_area.append(f"--- MESIN DIMULAI UNTUK AKUN {config['acc_num']} ---")
        
        self.thread = QThread()
        self.worker = Worker(config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.log_update.connect(self.log_area.append)
        self.thread.finished.connect(self.on_bot_finished)
        self.thread.start()
        
        self.update_toggle_button_ui(is_running=True)

    def stop_robot(self):
        if self.worker:
            self.worker.stop() # Ini akan memanggil fungsi stop() di logic_engulfing.py

    def on_bot_finished(self):
        """Fungsi yang dipanggil saat thread bot selesai."""
        self.log_area.append("Mesin telah menyelesaikan tugasnya.")
        self.update_toggle_button_ui(is_running=False)

        self.thread = None
        self.worker = None

QSS_STYLE = """
#MainContainer { background-color: #2c3e50; border-radius: 10px; }
#Header { background-color: #34495e; border-top-left-radius: 10px; border-top-right-radius: 10px; }
#HeaderTitle { font-size: 12pt; font-weight: bold; color: #ecf0f1; }
#WindowButton { background-color: #34495e; border: none; }
#WindowButton:hover { background-color: #49607a; border-radius: 5px; }
#WindowButton:pressed { background-color: #2c3e50; }
#StartButton { background-color: #27ae60; border: none; border-radius: 30px; }
#StartButton:hover { background-color: #2ecc71; }
#StopButton { background-color: #c0392b; border: none; border-radius: 30px; }
#StopButton:hover { background-color: #e74c3c; }
#ConnectButton { background-color: #3498db; color: white; font-weight: bold; border: none; border-radius: 5px; padding: 8px 15px; }
#ConnectButton:hover { background-color: #4ea8e1; }
#ConnectButton:pressed { background-color: #2980b9; }
#DisconnectButton {
    background-color: #7f8c8d; /* Warna abu-abu netral */
    color: white;
    font-weight: bold;
    border: none;
    border-radius: 5px;
    padding: 8px 15px;
}
#DisconnectButton:hover {
    background-color: #95a5a6;
}
#DisconnectButton:pressed {
    background-color: #626f70;
}
/* Styling untuk Tombol Stop */
#StopButton {
    background-color: #c0392b; /* Merah */
    border: 5px solid #e74c3c;
    border-radius: 40px; /* Kunci untuk membuatnya lingkaran */
}
#StopButton:hover {
    background-color: #e74c3c;
}
/* Styling untuk Tombol Stop */
#StopButton {
    background-color: #c0392b; /* Merah */
}
#StopButton:hover {
    background-color: #e74c3c;
}
#StopButton:pressed {
    background-color: #a93226;
}
QGroupBox { font-weight: bold; color: #2c3e50; border: 1px solid #bdc3c7; border-radius: 8px; margin-top: 1ex; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; background-color: #2c3e50; color: #ecf0f1; border-radius: 4px; }
QLabel { color: #2c3e50; font-weight: bold; background-color: transparent; }
QLineEdit, QComboBox, QDoubleSpinBox { background-color: #ffffff; color: #2c3e50; border: 1px solid #bdc3c7; border-radius: 5px; padding: 5px; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid #3498db; }
QTextEdit { background-color: #ecf0f1; border-radius: 5px; color: #2c3e50; }
"""

# QPushButton {
#     background-color: #3498db;
#     color: white;
#     font-weight: bold;
#     border: none;
#     border-radius: 5px;
#     padding: 8px 30px;
# }
# QPushButton:hover {
#     background-color: #4ea8e1;
# }
# QPushButton:pressed {
#     background-color: #2980b9;
# }


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 2. Cek keberadaan kunci sesi.
    session_key_found = any(arg.startswith('--session-key=') for arg in sys.argv)

    # 3. JIKA GAGAL: Tampilkan pop-up error dan keluar.
    if not session_key_found:
        # Buat kotak pesan error
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setWindowTitle("Akses Ditolak")
        error_box.setText("Aplikasi ini dilindungi.")
        error_box.setInformativeText("Harap jalankan aplikasi melalui Launcher resmi.")
        
        # Atur agar ikonnya tampil dengan benar
        # Ini adalah trik jika ikon utama belum di-set
        script_dir = os.path.dirname(os.path.realpath(__file__))
        icon_path = os.path.join(script_dir, "asset/icon/finance_icon.png")
        if os.path.exists(icon_path):
             error_box.setWindowIcon(QIcon(icon_path))

        error_box.exec() # Tampilkan pop-up dan tunggu hingga pengguna menutupnya
        sys.exit(1)
        
    # --- Trik untuk memaksa update ikon di taskbar Windows ---
    myappid = '7fxautomation.robot.m5eng1st.1'
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except AttributeError:
        pass

    app.setStyleSheet(QSS_STYLE)

    # --- Menerapkan Font Kustom ---
    font_path = resource_path("Roboto-Regular.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            app.setFont(QFont(font_family, 10))

    

    splash_path = resource_path("asset/icon/loader.gif")
    if os.path.exists(splash_path):
        # Buat label untuk menampung animasi
        splash_label = QLabel()
        splash_label.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        splash_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Muat dan jalankan animasi GIF
        movie = QMovie(splash_path)
        splash_label.setMovie(movie)
        movie.start()
        
        # Tampilkan splash screen di tengah layar
        splash_label.show()
    else:
        splash_label = None
        print(f"PERINGATAN: File splash screen '{splash_path}' tidak ditemukan.")

    # Buat instance window utama, tapi JANGAN ditampilkan dulu
    main_window = RobotApp()

    # Fungsi kecil untuk menutup splash dan menampilkan window utama
    def start_main_window():
        if splash_label:
            splash_label.close()
        main_window.show()

    # Gunakan QTimer agar animasi GIF tidak freeze
    # Setelah 3000 ms (3 detik), jalankan fungsi start_main_window
    QTimer.singleShot(3000, start_main_window)
    
    sys.exit(app.exec())