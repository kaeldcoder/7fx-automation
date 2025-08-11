import sys
import os
import json
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
                             QHBoxLayout, QLabel, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import qtawesome as qta

from report_viewer_window import ReportViewerWindow
from dashboard_widgets import KPIPanel
from report_analyzer import calculate_overall_kpis

class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        val1 = self.data(Qt.ItemDataRole.UserRole)
        val2 = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            return val1 < val2
        return super().__lt__(other)

class ReportDashboardWindow(QWidget):
    def __init__(self, reports_dir='reports', parent=None):
        super().__init__(parent)
        self.reports_dir = reports_dir
        self.viewer_windows = []
        self.all_reports_data = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 20, 30, 20)
        main_layout.setSpacing(20)

        toolbar_layout = QHBoxLayout()
        self.btn_refresh = QPushButton(qta.icon('fa5s.sync-alt', color='white'), self.tr(" Refresh List"))
        self.btn_refresh.setObjectName("AccountActionButton")
        self.btn_refresh.clicked.connect(self.refresh_data)
        toolbar_layout.addWidget(self.btn_refresh)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(QLabel(self.tr("Filter by:")))
        self.filter_date_combo = QComboBox()
        self.filter_date_combo.addItems([self.tr("All Time"), self.tr("Today"), self.tr("This Week"), self.tr("This Month")])
        self.filter_account_combo = QComboBox()
        toolbar_layout.addWidget(self.filter_date_combo)
        toolbar_layout.addWidget(self.filter_account_combo)
        main_layout.addLayout(toolbar_layout)

        self.kpi_panel = KPIPanel()
        self.kpi_panel.kpi_pnl.title_label.setText(self.tr("FILTERED P/L"))
        self.kpi_panel.kpi_pf.title_label.setText(self.tr("FILTERED PROFIT FACTOR"))
        self.kpi_panel.kpi_winrate.title_label.setText(self.tr("FILTERED WIN RATE"))
        self.kpi_panel.kpi_active_bots.icon_label.setPixmap(qta.icon('fa5s.history', color="#ffffff").pixmap(32, 32))
        self.kpi_panel.kpi_active_bots.title_label.setText(self.tr("FILTERED SESSIONS"))
        main_layout.addWidget(self.kpi_panel)

        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(7)
        self.table_widget.setHorizontalHeaderLabels([
            self.tr("Session Date"), self.tr("Account"), self.tr("Result (%)"), self.tr("Result ($)"), 
            self.tr("Win Rate"), self.tr("Profit Factor"), self.tr("Trades")
        ])
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.itemDoubleClicked.connect(self.open_report_viewer)
        main_layout.addWidget(self.table_widget)

        # Hubungkan sinyal filter ke fungsi update utama
        self.filter_date_combo.currentTextChanged.connect(self._apply_filters_and_update_ui)
        self.filter_account_combo.currentTextChanged.connect(self._apply_filters_and_update_ui)

        self.refresh_data()

    def refresh_data(self):
        """Membaca ulang semua file dan memperbarui seluruh UI."""
        self._load_all_reports()
        self._populate_account_filter()
        self._apply_filters_and_update_ui()

    def _apply_filters_and_update_ui(self):
        """Fungsi utama yang memfilter data dan mengupdate KPI + Tabel."""
        filtered_reports = self._get_filtered_reports()
        self._update_kpi_panel(filtered_reports)
        self._populate_table(filtered_reports)

    def _load_all_reports(self):
        """Membaca semua file JSON dari direktori dan menyimpannya di cache."""
        self.all_reports_data = []
        if not os.path.exists(self.reports_dir): return
        report_files = sorted(
            [f for f in os.listdir(self.reports_dir) if f.endswith('.json')],
            key=lambda x: os.path.getmtime(os.path.join(self.reports_dir, x)), reverse=True
        )
        for filename in report_files:
            filepath = os.path.join(self.reports_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data['meta_filepath'] = filepath
                    self.all_reports_data.append(data)
            except Exception as e:
                print(f"Warning: Failed to process report file '{filename}': {e}")

    def _populate_account_filter(self):
        """Mengisi dropdown filter akun dengan nomor akun unik."""
        current_selection = self.filter_account_combo.currentText()
        self.filter_account_combo.blockSignals(True)
        self.filter_account_combo.clear()
        accounts = {"All Accounts"}
        for report in self.all_reports_data:
            acc_num = report.get('summary', {}).get('account_number')
            if acc_num: accounts.add(str(acc_num))
        self.filter_account_combo.addItems(sorted(list(accounts)))
        if current_selection in accounts:
            self.filter_account_combo.setCurrentText(current_selection)
        self.filter_account_combo.blockSignals(False)

    def _get_filtered_reports(self) -> list:
        """Menerapkan filter aktif dan mengembalikan list data yang sesuai."""
        filtered_reports = self.all_reports_data
        
        selected_account = self.filter_account_combo.currentText()
        if selected_account and selected_account != "All Accounts":
            filtered_reports = [r for r in filtered_reports if str(r.get('summary', {}).get('account_number')) == selected_account]
        
        selected_date_filter = self.filter_date_combo.currentText()
        now = datetime.now()
        if selected_date_filter != "All Time":
            start_date = None
            if selected_date_filter == "Today": start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif selected_date_filter == "This Week": start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            elif selected_date_filter == "This Month": start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            if start_date:
                filtered_reports = [r for r in filtered_reports if datetime.fromisoformat(r.get('summary', {}).get('session_start_time')).replace(tzinfo=None) >= start_date]
        
        return filtered_reports

    def _update_kpi_panel(self, filtered_reports: list):
        """Memperbarui panel KPI HANYA dengan data yang sudah difilter."""
        kpis = calculate_overall_kpis(filtered_reports) # Gunakan fungsi yang sudah dimodifikasi
        
        pnl_value = kpis.get('total_pnl', 0.0)
        self.kpi_panel.kpi_pnl.set_value(f"${pnl_value:,.2f}")
        self.kpi_panel.kpi_pnl.set_value_color("#2ECC71" if pnl_value >= 0 else "#E74C3C")
        self.kpi_panel.kpi_pf.set_value(str(kpis.get('avg_profit_factor', 0.0)))
        self.kpi_panel.kpi_winrate.set_value(f"{kpis.get('overall_win_rate', 0.0):.2f}%")
        self.kpi_panel.kpi_active_bots.set_value(str(len(filtered_reports)))

    def _populate_table(self, filtered_reports: list):
        """Mengisi tabel HANYA dengan data yang sudah difilter."""
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(0)
        
        for report_data in filtered_reports:
            summary = report_data.get('summary', {})
            analytics = report_data.get('analytics', {})
            filepath = report_data.get('meta_filepath', '')
            pnl_percent_val, pnl_currency_val = float(summary.get('pnl_percent', 0)), float(summary.get('pnl_currency', 0))

            items_data = {
                0: {'text': datetime.fromisoformat(summary.get('session_start_time')).strftime('%Y-%m-%d %H:%M'), 'data': datetime.fromisoformat(summary.get('session_start_time')).timestamp(), 'numeric': False},
                1: {'text': str(summary.get('account_number', 'N/A')), 'data': int(summary.get('account_number', 0)), 'numeric': True},
                2: {'text': f"{pnl_percent_val:.2f}%", 'data': pnl_percent_val, 'numeric': True},
                3: {'text': f"${pnl_currency_val:,.2f}", 'data': pnl_currency_val, 'numeric': True},
                4: {'text': f"{summary.get('win_rate', 0):.2f}%", 'data': float(summary.get('win_rate', 0)), 'numeric': True},
                5: {'text': f"{analytics.get('profit_factor', 0)}", 'data': float(analytics.get('profit_factor', 0) if str(analytics.get('profit_factor')) != 'inf' else 999), 'numeric': True},
                6: {'text': str(summary.get('total_trades', 0)), 'data': int(summary.get('total_trades', 0)), 'numeric': True}
            }
            
            row_position = self.table_widget.rowCount()
            self.table_widget.insertRow(row_position)
            for col, item_info in items_data.items():
                item = NumericTableWidgetItem(item_info['text']) if item_info['numeric'] else QTableWidgetItem(item_info['text'])
                item.setData(Qt.ItemDataRole.UserRole, item_info['data'])
                if col == 0: item.setData(Qt.ItemDataRole.ToolTipRole, filepath)
                if item_info['numeric']: item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col in [2, 3] and item_info['data'] >= 0: item.setForeground(QColor("#2ECC71"))
                elif col in [2, 3] and item_info['data'] < 0: item.setForeground(QColor("#E74C3C"))
                self.table_widget.setItem(row_position, col, item)
        
        self.table_widget.setSortingEnabled(True)

    def open_report_viewer(self, item):
        filepath = self.table_widget.item(item.row(), 0).data(Qt.ItemDataRole.ToolTipRole)
        if not filepath: return
        viewer = ReportViewerWindow(filepath, self)
        self.viewer_windows.append(viewer)
        viewer.show()

    def setVisible(self, visible):
        super().setVisible(visible)
        if visible:
            self.refresh_data()