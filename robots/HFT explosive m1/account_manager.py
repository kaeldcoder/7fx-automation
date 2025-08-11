# account_manager.py

import os
import keyring
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QScrollArea, 
                             QMessageBox, QSpacerItem, QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt
import qtawesome as qta

# Impor widget dan dialog yang diperlukan
from custom_dialogs import ConfirmationDialog
from account_bubble_widget import AccountBubbleWidget
from edit_account_dialog import EditAccountDialog
from add_account_dialog import AddAccountDialog
from Library.utils.path_finder import load_accounts_data, save_accounts_data, load_known_paths

class AccountManager(QWidget):
    launch_panel_requested = pyqtSignal(dict)
    force_kill_requested = pyqtSignal(str)
    
    def __init__(self, robot_root_path: str, parent=None):
        super().__init__(parent)
        self.robot_root_path = robot_root_path
        self.bubbles = {} # Dictionary untuk melacak widget bubble

        # Layout utama
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 10) # Beri sedikit padding luar

        # --- Area Scroll untuk menampung semua bubble ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("BubbleScrollArea")
        
        # Widget kontainer di dalam scroll area
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("BubbleScrollContainer")
        self.bubble_layout = QVBoxLayout(self.scroll_content)
        self.bubble_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.bubble_layout.setContentsMargins(0, 0, 0, 0)
        self.bubble_layout.setSpacing(15) # Jarak antar bubble

        # Spacer ini akan mendorong tombol "Add Account" ke bawah
        self.spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.bubble_layout.addSpacerItem(self.spacer)

        # Tombol "Add Account" yang mengambang
        self.btn_add = QPushButton(qta.icon('fa5s.plus', color='#FFFFFF'), self.tr(" Add New Account"))
        self.btn_add.setObjectName("FloatingAddButton")
        self.btn_add.clicked.connect(self.add_new_account)
        self.bubble_layout.addWidget(self.btn_add)

        scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(scroll_area)
        
        self.load_account_data()

    def load_account_data(self):
        for bubble in self.bubbles.values():
            bubble.deleteLater()
        self.bubbles.clear()
        accounts = load_accounts_data(self.robot_root_path)
        
        for i, (acc_num, acc_info) in enumerate(accounts.items()):
            bubble = AccountBubbleWidget(acc_num, acc_info)
            
            bubble.launch_requested.connect(self.request_launch_control_panel)
            bubble.edit_requested.connect(self.edit_selected_account)
            bubble.delete_requested.connect(self.delete_selected_account)
            bubble.kill_requested.connect(self.request_force_kill)
            
            self.bubble_layout.insertWidget(i, bubble)
            self.bubbles[acc_num] = bubble

    def request_force_kill(self, account_number: str):
        """Meneruskan permintaan kill dari bubble ke main dashboard."""
        self.force_kill_requested.emit(account_number)

    def add_new_account(self):
        # (Fungsi ini hampir sama, hanya print() yang disesuaikan)
        all_paths = load_known_paths(self.robot_root_path)
        dialog = AddAccountDialog(self.robot_root_path, all_paths, self)

        if dialog.exec():
            new_info = dialog.get_new_account_info()
            if not new_info:
                QMessageBox.warning(self, self.tr("Incomplete Input"), self.tr("All fields must be filled."))
                return

            account_number = new_info['number']
            all_accounts_data = load_accounts_data(self.robot_root_path)

            if account_number in all_accounts_data:
                QMessageBox.warning(self, self.tr("Failed"), self.tr("Account {0} is already registered.").format(account_number))
                return

            all_accounts_data[account_number] = {'server': new_info['server'], 'path': new_info['path']}
            save_accounts_data(self.robot_root_path, all_accounts_data)

            if new_info['save_password']:
                try:
                    keyring.set_password("7FX_HFT_Bot", account_number, new_info['password'])
                except Exception as e:
                    QMessageBox.critical(self, self.tr("Failed to Save Password"), self.tr("Failed to save password to Keyring: {0}").format(e))

            self.load_account_data() # Muat ulang semua bubble

    def edit_selected_account(self, account_number: str):
        # (Fungsi ini diubah untuk menerima account_number langsung dari sinyal bubble)
        all_accounts_data = load_accounts_data(self.robot_root_path)
        all_paths = load_known_paths(self.robot_root_path)

        current_account_info = all_accounts_data.get(account_number, {})
        current_account_info['number'] = account_number
        if 'path' not in current_account_info:
            current_account_info['path'] = list(all_paths)[0] if all_paths else ""

        dialog = EditAccountDialog(current_account_info, list(all_paths), self)
        if dialog.exec():
            updated_info = dialog.get_updated_info()
            all_accounts_data[account_number] = {'server': updated_info.get('server'), 'path': updated_info.get('path')}
            save_accounts_data(self.robot_root_path, all_accounts_data)
            self.load_account_data() # Muat ulang semua bubble

    def delete_selected_account(self, account_number: str):
        dialog = ConfirmationDialog(
            title=self.tr("Confirm Deletion"),
            message=self.tr("Are you sure you want to permanently delete account {0}?\nThis action cannot be undone.").format(account_number),
            parent=self
        )
        if dialog.exec():
            all_accounts_data = load_accounts_data(self.robot_root_path)
            if account_number in all_accounts_data:
                del all_accounts_data[account_number]
                save_accounts_data(self.robot_root_path, all_accounts_data)
                try:
                    keyring.delete_password("7FX_HFT_Bot", account_number)
                except Exception:
                    pass
                self.load_account_data() # Muat ulang semua bubble
            else:
                QMessageBox.critical(self, self.tr("Error"), self.tr("Account {0} not found in data file.").format(account_number))

    def request_launch_control_panel(self, account_number: str):
        # (Fungsi ini diubah untuk menerima account_number langsung dari sinyal bubble)
        all_accounts_data = load_accounts_data(self.robot_root_path)
        account_info = all_accounts_data.get(account_number, {})
        account_info['number'] = account_number
        self.launch_panel_requested.emit(account_info)
        
    def update_account_status(self, account_number: str, status: str):
        """Menemukan bubble yang tepat dan memanggil metode update statusnya."""
        if account_number in self.bubbles:
            self.bubbles[account_number].update_status(status)