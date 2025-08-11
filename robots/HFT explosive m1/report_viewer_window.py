# robots/HFT explosive m1/report_viewer_window.py

import sys
import os
import json
import pandas as pd
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, 
                             QMessageBox, QLabel, QGroupBox, QComboBox, QTableView, QFileDialog)
from PyQt6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel
import pyqtgraph as pg

# --- Model Data Kustom untuk Tabel (Penting untuk Performa & Filtering) ---
class TradeTableModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent):
        return self._data.shape[0]

    def columnCount(self, parent):
        return self._data.shape[1]

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            # Formatting khusus untuk kolom tertentu
            if isinstance(value, float):
                return f"{value:.5f}" if "price" in self._data.columns[index.column()] else f"{value:.2f}"
            if "time" in self._data.columns[index.column()]:
                 return datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')
            return str(value)
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.tr(str(self._data.columns[section]))
        return None

# --- Jendela Utama Viewer ---
class ReportViewerWindow(QDialog):
    def __init__(self, json_filepath, parent=None):
        super().__init__(parent)
        
        if not os.path.exists(json_filepath):
            QMessageBox.critical(self, self.tr("Error"), self.tr("Report file not found:\n{0}").format(json_filepath))
            return
            
        with open(json_filepath, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        self.setWindowTitle(self.tr("Session Report Details - Account {0}").format(self.data['summary']['account_number']))
        self.setGeometry(350, 250, 1200, 800)
        
        # --- Siapkan Data Awal ---
        self.trades_df = pd.DataFrame(self.data['trades'])
        # Menambahkan kolom profit untuk filter
        self.trades_df['profit_val'] = pd.to_numeric(self.trades_df['profit'])


        # --- Layout Utama ---
        main_layout = QVBoxLayout(self)
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)

        # --- Panel Kiri (Ringkasan & Grafik) ---
        left_panel_layout = QVBoxLayout()
        top_layout.addLayout(left_panel_layout, 1) # Stretch factor 1

        # --- Panel Kanan (Tabel & Filter) ---
        right_panel_layout = QVBoxLayout()
        top_layout.addLayout(right_panel_layout, 2) # Stretch factor 2 (lebih besar)

        # --- Isi Panel Kiri ---
        left_panel_layout.addWidget(self._create_summary_panel())
        left_panel_layout.addWidget(self._create_charts_panel())
        
        # --- Isi Panel Kanan ---
        right_panel_layout.addWidget(self._create_table_panel())

        self._populate_data()

    def _create_summary_panel(self):
        summary_group = QGroupBox(self.tr("Performance Summary"))
        grid = QGridLayout(summary_group)
        
        self.summary_labels = {
            self.tr("Session P/L ($)"): QLabel("-"), self.tr("Session P/L (%)"): QLabel("-"),
            self.tr("Profit Factor"): QLabel("-"), self.tr("Win Rate (%)"): QLabel("-"),
            self.tr("Total Trades"): QLabel("-"), self.tr("Expectancy/Trade"): QLabel("-")
        }
        
        positions = [(i, j) for i in range(3) for j in range(2)]
        for (key, label), pos in zip(self.summary_labels.items(), positions):
            title_label = QLabel(f"<b>{key}</b>")
            grid.addWidget(title_label, pos[0], pos[1]*2)
            grid.addWidget(label, pos[0], pos[1]*2 + 1)
            
        return summary_group
        
    def _create_charts_panel(self):
        charts_group = QGroupBox(self.tr("Performance Charts"))
        layout = QVBoxLayout(charts_group)
        
        # Grafik Kurva Ekuitas
        self.equity_curve_widget = pg.PlotWidget()
        self.equity_curve_widget.setBackground('w')
        self.equity_curve_widget.setTitle(self.tr("Cumulative P/L Curve"))
        self.equity_curve_widget.setLabel('left', self.tr("Profit/Loss ($)"))
        self.equity_curve_widget.setLabel('bottom', self.tr("Trade Number"))
        self.equity_curve_widget.showGrid(x=True, y=True)
        layout.addWidget(self.equity_curve_widget)
        
        return charts_group

    def _create_table_panel(self):
        table_group = QGroupBox(self.tr("Transaction Details"))
        layout = QVBoxLayout(table_group)
        
        # Filter Controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel(self.tr("Filter Symbol:")))
        self.symbol_filter = QComboBox()
        filter_layout.addWidget(self.symbol_filter)

        filter_layout.addSpacing(20) # Beri sedikit jarak
        filter_layout.addWidget(QLabel(self.tr("Filter Strategy:")))
        self.strategy_filter = QComboBox()
        filter_layout.addWidget(self.strategy_filter)
        
        self.btn_filter_all = QPushButton(self.tr("All"))
        self.btn_filter_win = QPushButton(self.tr("Profit"))
        self.btn_filter_loss = QPushButton(self.tr("Loss"))
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_filter_all)
        filter_layout.addWidget(self.btn_filter_win)
        filter_layout.addWidget(self.btn_filter_loss)
        layout.addLayout(filter_layout)

        # Tabel
        self.table_view = QTableView()
        self.table_model = TradeTableModel(self.trades_df)
        
        # Proxy Model untuk Filtering
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)
        
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table_view)
        
        # Tombol Ekspor
        self.btn_export_csv = QPushButton(self.tr("Export to CSV"))
        layout.addWidget(self.btn_export_csv, 0, Qt.AlignmentFlag.AlignRight)
        
        # Hubungkan sinyal
        self.symbol_filter.currentTextChanged.connect(self._filter_table)
        self.btn_filter_all.clicked.connect(lambda: self._filter_table(outcome='all'))
        self.btn_filter_win.clicked.connect(lambda: self._filter_table(outcome='win'))
        self.btn_filter_loss.clicked.connect(lambda: self._filter_table(outcome='loss'))
        self.btn_export_csv.clicked.connect(self._export_to_csv)

        return table_group

    def _populate_data(self):
        summary = self.data['summary']
        analytics = self.data['analytics']

        # Isi panel ringkasan
        self.summary_labels["P/L Sesi ($)"].setText(f"<font color='{'green' if summary['pnl_currency'] >= 0 else 'red'}'>{summary['pnl_currency']:.2f}</font>")
        self.summary_labels["P/L Sesi (%)"].setText(f"<font color='{'green' if summary['pnl_percent'] >= 0 else 'red'}'>{summary['pnl_percent']:.2f}%</font>")
        self.summary_labels["Profit Factor"].setText(f"<b>{analytics['profit_factor']}</b>")
        self.summary_labels["Win Rate (%)"].setText(f"<b>{summary['win_rate']:.2f}%</b>")
        self.summary_labels["Total Trade"].setText(f"<b>{summary['total_trades']}</b>")
        self.summary_labels["Ekspektasi/Trade"].setText(f"<b>{analytics['expectancy_per_trade']:.2f}</b>")
        
        # Isi Grafik
        if not self.trades_df.empty:
            pnl_cumulative = self.trades_df['profit_val'].cumsum()
            self.equity_curve_widget.plot(pnl_cumulative.tolist(), pen=pg.mkPen(color='#007bff', width=2))

        # Isi filter simbol
        symbols = ['Semua Simbol'] + self.trades_df['symbol'].unique().tolist()
        self.symbol_filter.addItems(symbols)

        if 'strategy' in self.trades_df.columns:
            strategies = ['Semua Strategi'] + self.trades_df['strategy'].unique().tolist()
            self.strategy_filter.addItems(strategies)
        else:
            self.strategy_filter.hide() # Sembunyikan jika data lama tidak punya info strategi
            self.findChild(QLabel, "Filter Strategi:").hide()

    def _filter_table(self, text=None, outcome=None):
        # Kelas custom untuk filter win/loss
        class OutcomeFilterProxyModel(QSortFilterProxyModel):
            def __init__(self, outcome_filter):
                super().__init__()
                self.outcome_filter = outcome_filter

            def filterAcceptsRow(self, source_row, source_parent):
                if self.outcome_filter == 'all':
                    return True
                profit_index = self.sourceModel()._data.columns.get_loc('profit_val')
                profit_val = self.sourceModel()._data.iloc[source_row, profit_index]
                if self.outcome_filter == 'win':
                    return profit_val >= 0
                if self.outcome_filter == 'loss':
                    return profit_val < 0
                return True

        # Terapkan filter berdasarkan input
        current_symbol = self.symbol_filter.currentText()
        current_strategy = self.strategy_filter.currentText()

        # Buat filter boolean untuk setiap kondisi
        symbol_mask = True
        if current_symbol != 'Semua Simbol':
            symbol_mask = self.table_model._data['symbol'] == current_symbol

        strategy_mask = True
        if hasattr(self, 'strategy_filter') and self.strategy_filter.currentText() != 'Semua Strategi':
            strategy_mask = self.table_model._data['strategy'] == current_strategy

        # Gabungkan semua filter
        combined_mask = symbol_mask & strategy_mask

        # Terapkan filter menggunakan proxy model
        class DynamicFilterProxyModel(QSortFilterProxyModel):
            def __init__(self, mask):
                super().__init__()
                self.mask = mask

            def filterAcceptsRow(self, source_row, source_parent):
                return self.mask.iloc[source_row]

        # Buat proxy model baru dengan filter win/loss
        self.proxy_model = DynamicFilterProxyModel(combined_mask)
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)
        
        # Terapkan filter simbol
        if current_symbol != 'Semua Simbol':
            symbol_col_index = self.table_model._data.columns.get_loc('symbol')
            self.proxy_model.setFilterKeyColumn(symbol_col_index)
            self.proxy_model.setFilterFixedString(current_symbol)
            
        self.table_view.setModel(self.proxy_model)

    def _export_to_csv(self):
        # Ambil data yang sedang ditampilkan di tabel
        visible_rows = self.proxy_model.rowCount(None)
        if visible_rows == 0:
            QMessageBox.information(self, self.tr("Info"), self.tr("No data to export."))
            return
            
        # Dapatkan path untuk menyimpan file
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Save as CSV"), "", self.tr("CSV Files (*.csv)"))
        
        if path:
            # Buat DataFrame dari data yang terfilter
            indices = [self.proxy_model.mapToSource(self.proxy_model.index(row, 0)).row() for row in range(visible_rows)]
            filtered_df = self.table_model._data.iloc[indices]
            
            try:
                filtered_df.to_csv(path, index=False)
                QMessageBox.information(self, self.tr("Success"), self.tr("Data successfully exported to:\n{0}").format(path))
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to export data: {0}").format(e))
