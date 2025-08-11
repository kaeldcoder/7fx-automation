# global_settings_dialog.py

import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, 
                             QCheckBox, QPushButton, QLineEdit, QDialogButtonBox,
                             QHBoxLayout, QFileDialog, QGroupBox, QTabWidget, QWidget,
                             QComboBox)
from PyQt6.QtCore import QSettings, QUrl
from PyQt6.QtGui import QDesktopServices
import qtawesome as qta

class GlobalSettingsDialog(QWidget): # <-- Ubah dari QDialog menjadi QWidget
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings('7FXAutomation', 'MainDashboard')

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 20, 30, 20) # Beri padding luar

        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), self.tr("General"))
        tabs.addTab(self._create_notifications_tab(), self.tr("Notifications"))
        main_layout.addWidget(tabs)

        # Tombol tidak lagi diperlukan di sini karena ini adalah halaman, bukan dialog
        # button_box = QDialogButtonBox(...)

        self.load_settings()
        # Hubungkan sinyal setelah load_settings agar tidak ter-trigger saat inisialisasi
        self._connect_signals()

    def _create_general_tab(self):
        general_widget = QWidget()
        layout = QVBoxLayout(general_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)
        
        # --- Grup Perilaku Aplikasi ---
        behavior_group = QGroupBox(self.tr("Application Behavior"))
        # [DIUBAH] Gunakan QGridLayout untuk perataan
        behavior_layout = QGridLayout(behavior_group)
        behavior_layout.setColumnStretch(1, 1) # Kolom input lebih lebar
        behavior_layout.setVerticalSpacing(15)

        self.confirm_on_exit_checkbox = QCheckBox(self.tr("Show confirmation on exit if bots are running"))
        self.close_behavior_combo = QComboBox()
        self.close_behavior_combo.addItems([self.tr("Hide to System Tray"), self.tr("Close Application Completely")])
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.tr("Dark (Default)")]) # Tema hanya Dark untuk saat ini
        self.theme_combo.setEnabled(False) 

        behavior_layout.addWidget(self.confirm_on_exit_checkbox, 0, 0, 1, 2) # Checkbox mengambil 2 kolom
        behavior_layout.addWidget(QLabel(self.tr("When [X] is pressed:")), 1, 0)
        behavior_layout.addWidget(self.close_behavior_combo, 1, 1)
        behavior_layout.addWidget(QLabel(self.tr("Application Theme:")), 2, 0)
        behavior_layout.addWidget(self.theme_combo, 2, 1)
        
        layout.addWidget(behavior_group)

        # --- Grup Lokasi Data ---
        paths_group = QGroupBox(self.tr("Data Locations"))
        paths_layout = QGridLayout(paths_group)
        paths_layout.setColumnStretch(1, 1)
        paths_layout.setVerticalSpacing(15)

        self.reports_path_input = QLineEdit()
        self.btn_browse_reports = QPushButton(qta.icon('fa5s.folder-open', color='white'), "")
        self.btn_browse_reports.setObjectName("BrowseButton") # Beri nama untuk styling
        self.configs_path_input = QLineEdit()
        self.btn_browse_configs = QPushButton(qta.icon('fa5s.folder-open', color='white'), "")
        self.btn_browse_configs.setObjectName("BrowseButton")

        paths_layout.addWidget(QLabel(self.tr("Reports Folder:")), 0, 0)
        paths_layout.addLayout(self._create_browse_layout(self.reports_path_input, self.btn_browse_reports), 0, 1)
        
        paths_layout.addWidget(QLabel(self.tr("Configs Folder:")), 1, 0)
        paths_layout.addLayout(self._create_browse_layout(self.configs_path_input, self.btn_browse_configs), 1, 1)

        self.btn_browse_reports.clicked.connect(lambda: self._browse_folder(self.reports_path_input, self.tr("Select Reports Folder")))
        self.btn_browse_configs.clicked.connect(lambda: self._browse_folder(self.configs_path_input, self.tr("Select Configurations Folder")))

        layout.addWidget(paths_group)
        layout.addStretch()

        return general_widget

    def _create_notifications_tab(self):
        notifications_widget = QWidget()
        layout = QVBoxLayout(notifications_widget)
        layout.setContentsMargins(15, 15, 15, 15)

        community_group = QGroupBox(self.tr("Community & Support"))
        community_layout = QVBoxLayout(community_group)
        
        info_label = QLabel(self.tr("Join our Telegram group to get the latest updates, support, and discuss with other users."))
        info_label.setWordWrap(True)
        
        self.btn_join_telegram = QPushButton(qta.icon('fa5b.telegram-plane', color='#29A9EA'), self.tr(" Join Telegram Group"))
        self.btn_join_telegram.setObjectName("TelegramButton") # Beri nama untuk styling
        self.btn_join_telegram.clicked.connect(self._open_telegram_link)
        
        community_layout.addWidget(info_label)
        community_layout.addSpacing(10)
        community_layout.addWidget(self.btn_join_telegram)
        
        layout.addWidget(community_group)
        layout.addStretch()
        
        return notifications_widget

    def _connect_signals(self):
        """Menghubungkan semua sinyal ke fungsi save."""
        self.confirm_on_exit_checkbox.stateChanged.connect(self.save_settings)
        self.close_behavior_combo.currentIndexChanged.connect(self.save_settings)
        self.reports_path_input.editingFinished.connect(self.save_settings)
        self.configs_path_input.editingFinished.connect(self.save_settings)

    def load_settings(self):
        """Membaca pengaturan dari QSettings dan menerapkannya ke UI."""
        self.confirm_on_exit_checkbox.setChecked(self.settings.value('show_exit_confirmation', True, type=bool))
        self.close_behavior_combo.setCurrentIndex(self.settings.value('close_behavior', 0, type=int))
        self.theme_combo.setCurrentText(self.settings.value('theme', 'Dark (Default)', type=str))
        
        default_reports_path = os.path.abspath('reports')
        default_configs_path = os.path.abspath('configs')

        self.reports_path_input.setText(self.settings.value('reports_path', default_reports_path, type=str))
        self.configs_path_input.setText(self.settings.value('configs_path', default_configs_path, type=str))

    def save_settings(self):
        """Menyimpan pengaturan dari UI ke QSettings secara otomatis."""
        self.settings.setValue('show_exit_confirmation', self.confirm_on_exit_checkbox.isChecked())
        self.settings.setValue('close_behavior', self.close_behavior_combo.currentIndex())
        self.settings.setValue('theme', self.theme_combo.currentText())
        self.settings.setValue('reports_path', self.reports_path_input.text())
        self.settings.setValue('configs_path', self.configs_path_input.text())
        print("Settings saved.") # Feedback untuk debugging

    def _create_browse_layout(self, line_edit, button):
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(10)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return layout

    def _browse_folder(self, line_edit, caption):
        directory = QFileDialog.getExistingDirectory(self, caption, line_edit.text())
        if directory:
            line_edit.setText(directory)
            self.save_settings() # Simpan langsung setelah memilih folder baru

    def _open_telegram_link(self):
        url = QUrl("https://t.me/your_robot_group_name") # Ganti dengan link Anda
        QDesktopServices.openUrl(url)