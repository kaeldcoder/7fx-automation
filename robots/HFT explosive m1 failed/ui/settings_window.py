import json
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QTabWidget, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QDoubleSpinBox, 
                             QSpinBox, QMessageBox, QCompleter, QDialog, QCheckBox, QTimeEdit, QGroupBox)
from PyQt6.QtCore import Qt, QTime, pyqtSignal
import qtawesome as qta
import MetaTrader5 as mt5
import pytz
import importlib
import inspect
import re

def camel_to_snake(name):
    """Mengubah NamaKelas (CamelCase) menjadi nama_kelas (snake_case) untuk nama file."""
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TIMEFRAME_MAP = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, 
                "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}

def load_available_strategies():
    """Memindai folder strategies dan memuat semua kelas strategi yang valid."""
    strategies = {}
    strategy_path = os.path.join(project_root, "Library", "strategies")
    
    for filename in os.listdir(strategy_path):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]
            module = importlib.import_module(f"Library.strategies.{module_name}")
            
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, 'strategy_name'):
                    # Simpan nama kelas sebagai kunci dan nama tampilan sebagai nilai
                    strategies[name] = obj.strategy_name
    return strategies

def load_available_exit_strategies():
    """Memindai folder exit_strategies dan memuat semua kelas exit strategy."""
    exit_strategies = {}
    exit_strategy_path = os.path.join(project_root, "Library", "exit_strategies")
    if not os.path.exists(exit_strategy_path): return {}

    for filename in os.listdir(exit_strategy_path):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]
            module = importlib.import_module(f"Library.exit_strategies.{module_name}")
            
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, 'exit_name'):
                    exit_strategies[name] = obj.exit_name
    return exit_strategies

class AccountManagerTab(QWidget):
    config_changed = pyqtSignal()
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)

        settings_group = QGroupBox("Pengaturan Manajemen")
        layout = QGridLayout(settings_group)
        layout.setColumnStretch(1, 1); layout.setColumnStretch(2, 1)
        
        self.widgets = {}
        self._create_dynamic_target_widget(layout, 0, "Target Profit Sesi", "profit_target")
        self._create_dynamic_target_widget(layout, 1, "Batas Loss Sesi", "loss_target")
        self._create_dynamic_target_widget(layout, 2, "Stop Ekuitas Absolut", "absolute_equity_stop", has_percent=True)

        layout.addWidget(QLabel("Mode Drawdown:"), 3, 0)
        self.widgets["drawdown_mode"] = QComboBox(); self.widgets["drawdown_mode"].addItems(["peak_equity", "initial_balance"])
        layout.addWidget(self.widgets["drawdown_mode"], 3, 1, 1, 2)
        
        self.widgets["use_gradual_stop"] = QCheckBox(); self.widgets["gradual_stop_percent"] = QDoubleSpinBox()
        layout.addWidget(QLabel("Gunakan Gradual Stop:"), 4, 0); layout.addWidget(self.widgets["use_gradual_stop"], 4, 1)
        layout.addWidget(QLabel("  └─ Level Gradual Stop (%):"), 5, 0); layout.addWidget(self.widgets["gradual_stop_percent"], 5, 1, 1, 2)

        self.widgets["use_consecutive_loss_stop"] = QCheckBox(); self.widgets["max_consecutive_losses"] = QSpinBox()
        layout.addWidget(QLabel("Gunakan Stop Loss Beruntun:"), 6, 0); layout.addWidget(self.widgets["use_consecutive_loss_stop"], 6, 1)
        layout.addWidget(QLabel("  └─ Jumlah Loss Beruntun:"), 7, 0); layout.addWidget(self.widgets["max_consecutive_losses"], 7, 1, 1, 2)
        
        self.widgets["use_gradual_stop"].toggled.connect(self.widgets["gradual_stop_percent"].setEnabled)
        self.widgets["use_consecutive_loss_stop"].toggled.connect(self.widgets["max_consecutive_losses"].setEnabled)
        
        layout.addWidget(QLabel("Zona Waktu (Timezone):"), 8, 0)
        self.widgets["timezone"] = QComboBox()
        common_timezones = sorted([tz for tz in pytz.common_timezones if any(c in tz for c in ["Asia", "Etc", "UTC", "Europe", "America"])])
        self.widgets["timezone"].addItems(common_timezones)
        layout.addWidget(self.widgets["timezone"], 8, 1, 1, 2)
        
        layout.addWidget(QLabel("Mode Cooldown:"), 9, 0)
        self.widgets["cooldown_mode"] = QComboBox(); self.widgets["cooldown_mode"].addItems(["next_day_at", "duration", "next_candle"])
        layout.addWidget(self.widgets["cooldown_mode"], 9, 1, 1, 2)

        self._create_cooldown_details_widgets(layout, 10)
        self.widgets["cooldown_mode"].currentTextChanged.connect(self._update_cooldown_ui)
        self._update_cooldown_ui(self.widgets["cooldown_mode"].currentText())

        main_layout.addWidget(settings_group)

        trade_control_group = QGroupBox("Pengaturan Kontrol Order")
        trade_layout = QGridLayout(trade_control_group)
        trade_layout.setColumnStretch(1, 1)

        # 1. Maksimal Trade Berjalan
        trade_layout.addWidget(QLabel("Maksimal Trade Berjalan:"), 0, 0)
        self.widgets["max_concurrent_trades"] = QSpinBox()
        self.widgets["max_concurrent_trades"].setRange(1, 100)
        self.widgets["max_concurrent_trades"].setToolTip("Jumlah maksimal posisi yang boleh terbuka secara bersamaan.")
        trade_layout.addWidget(self.widgets["max_concurrent_trades"], 0, 1)
        
        # 2. Jeda Antar Order
        trade_layout.addWidget(QLabel("Jeda Antar Order (detik):"), 1, 0)
        self.widgets["order_cooldown_seconds"] = QDoubleSpinBox()
        self.widgets["order_cooldown_seconds"].setRange(0.5, 60.0)
        self.widgets["order_cooldown_seconds"].setSingleStep(0.5)
        self.widgets["order_cooldown_seconds"].setToolTip("Waktu jeda minimal antar penempatan order baru.")
        trade_layout.addWidget(self.widgets["order_cooldown_seconds"], 1, 1)

        main_layout.addWidget(trade_control_group)

        for widget in self.widgets.values():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.valueChanged.connect(self.config_changed.emit)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self.config_changed.emit)
        
    def _create_dynamic_target_widget(self, layout, row, label_text, key, has_percent=True):
        self.widgets[f"{key}_value"] = QDoubleSpinBox(); self.widgets[f"{key}_value"].setRange(0, 1000000)
        self.widgets[f"{key}_type"] = QComboBox()
        options = ["Amount ($)"]
        if has_percent: options.append("Percent (%)")
        self.widgets[f"{key}_type"].addItems(options)
        layout.addWidget(QLabel(f"{label_text}:"), row, 0)
        layout.addWidget(self.widgets[f"{key}_value"], row, 1)
        layout.addWidget(self.widgets[f"{key}_type"], row, 2)

    def _create_cooldown_details_widgets(self, layout, start_row):
        self.widgets["cooldown_duration_hours"] = QSpinBox(); self.widgets["cooldown_duration_minutes"] = QSpinBox()
        self.widgets["cooldown_next_day_time"] = QTimeEdit(QTime(8,0))
        timeframe_map_rev = {v: k for k, v in TIMEFRAME_MAP.items()}
        self.widgets["cooldown_next_candle_tf"] = QComboBox()
        self.widgets["cooldown_next_candle_tf"].addItems(timeframe_map_rev.values())
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(self.widgets["cooldown_duration_hours"]); duration_layout.addWidget(QLabel("Jam"))
        duration_layout.addWidget(self.widgets["cooldown_duration_minutes"]); duration_layout.addWidget(QLabel("Menit"))
        self.duration_container = QWidget(); self.duration_container.setLayout(duration_layout)
        layout.addWidget(QLabel("  └─ Detail:"), start_row, 0)
        layout.addWidget(self.duration_container, start_row, 1, 1, 2)
        layout.addWidget(self.widgets["cooldown_next_day_time"], start_row, 1, 1, 2)
        layout.addWidget(self.widgets["cooldown_next_candle_tf"], start_row, 1, 1, 2)

    def _update_cooldown_ui(self, mode):
        self.duration_container.setVisible(mode == 'duration')
        self.widgets["cooldown_next_day_time"].setVisible(mode == 'next_day_at')
        self.widgets["cooldown_next_candle_tf"].setVisible(mode == 'next_candle')

    def get_config(self) -> dict:
        config = {}
        # Ambil nilai non-dinamis dulu
        simple_widgets = ["drawdown_mode", "use_gradual_stop", "gradual_stop_percent", 
                          "use_consecutive_loss_stop", "max_consecutive_losses", "timezone", "cooldown_mode"]
        for key in simple_widgets:
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, QCheckBox): config[key] = widget.isChecked()
                elif isinstance(widget, QComboBox): config[key] = widget.currentText()
                else: config[key] = widget.value()

        # Ambil nilai dari widget dinamis
        for key in ["profit_target", "loss_target", "absolute_equity_stop"]:
            config[key] = {
                "value": self.widgets[f"{key}_value"].value(),
                "type": "percent" if self.widgets[f"{key}_type"].currentText() == "Percent (%)" else "amount"
            }
        
        # Susun config cooldown
        mode = config.get("cooldown_mode", "duration")
        cooldown_details = {"mode": mode}
        if mode == 'duration':
            cooldown_details['hours'] = self.widgets["cooldown_duration_hours"].value()
            cooldown_details['minutes'] = self.widgets["cooldown_duration_minutes"].value()
        elif mode == 'next_day_at':
            cooldown_details['time'] = self.widgets["cooldown_next_day_time"].time().toString("HH:mm")
        elif mode == 'next_candle':
            cooldown_details['timeframe'] = TIMEFRAME_MAP.get(self.widgets["cooldown_next_candle_tf"].currentText(), mt5.TIMEFRAME_H1)
        config['cooldown_config'] = cooldown_details
        for key in ["max_concurrent_trades", "order_cooldown_seconds"]:
             if key in self.widgets:
                config[key] = self.widgets[key].value()
        return config

    def set_config(self, config_data: dict):
        """[FINAL] Mengisi semua widget dengan data dari file config yang dimuat."""
        # Isi widget dinamis
        for key in ["profit_target", "loss_target", "absolute_equity_stop"]:
            if key in config_data:
                self.widgets[f"{key}_value"].setValue(config_data[key].get("value", 0))
                type_text = "Percent (%)" if config_data[key].get("type") == "percent" else "Amount ($)"
                self.widgets[f"{key}_type"].setCurrentText(type_text)

        # Isi widget lain dengan tipe data yang benar
        for key, value in config_data.items():
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QComboBox) and key not in ["cooldown_mode", "timezone"]:
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QSpinBox):
                    # [PERBAIKAN] Konversi nilai ke integer sebelum di-set
                    widget.setValue(int(float(value)))
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
        
        # Atur Timezone
        if 'timezone' in config_data:
            self.widgets['timezone'].setCurrentText(config_data['timezone'])

        # Atur Cooldown Config
        cooldown_cfg = config_data.get('cooldown_config', {})
        if 'mode' in cooldown_cfg:
            self.widgets['cooldown_mode'].setCurrentText(cooldown_cfg['mode'])
            
            if cooldown_cfg['mode'] == 'duration':
                self.widgets['cooldown_duration_hours'].setValue(int(cooldown_cfg.get('hours', 1)))
                self.widgets['cooldown_duration_minutes'].setValue(int(cooldown_cfg.get('minutes', 0)))
            elif cooldown_cfg['mode'] == 'next_day_at':
                self.widgets['cooldown_next_day_time'].setTime(QTime.fromString(cooldown_cfg.get('time', '08:00'), "HH:mm"))
            elif cooldown_cfg['mode'] == 'next_candle':
                tf_value = cooldown_cfg.get('timeframe')
                timeframe_map_rev = {v: k for k, v in TIMEFRAME_MAP.items()}
                self.widgets['cooldown_next_candle_tf'].setCurrentText(timeframe_map_rev.get(tf_value, 'H1'))
        
        self.widgets['max_concurrent_trades'].setValue(config_data.get('max_concurrent_trades', 1))
        self.widgets['order_cooldown_seconds'].setValue(config_data.get('order_cooldown_seconds', 1.0))

# --- Widget Kustom untuk Pengaturan per Pair ---
class StrategyTab(QWidget):
    symbol_selection_changed = pyqtSignal()
    def __init__(self, available_symbols: list, initial_magic: int, 
                 entry_strategy_map: dict, exit_strategy_map: dict):
        super().__init__()
        # Simpan peta nama kelas -> nama tampilan & peta nama kelas -> definisi parameter
        self.available_symbols = available_symbols
        self.entry_strategy_map = entry_strategy_map
        self.exit_strategy_map = exit_strategy_map
        self.entry_strategy_params = self._load_parameters(entry_strategy_map, "strategies")
        self.exit_strategy_params = self._load_parameters(exit_strategy_map, "exit_strategies")

        # Layout utama
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        # --- Widget statis yang selalu ada ---
        entry_group = QGroupBox("Pengaturan Entri")
        entry_layout = QGridLayout(entry_group)
        self.main_layout.addWidget(entry_group)

        # Widget statis (selalu ada)
        self.strategy_combo = QComboBox()
        for display_name in self.entry_strategy_map.values():
            self.strategy_combo.addItem(display_name)
        entry_layout.addWidget(QLabel("Strategi Entri:"), 0, 0)
        entry_layout.addWidget(self.strategy_combo, 0, 1)

        self.symbol_combo = QComboBox()
        self.symbol_combo.setEditable(True)
        self.symbol_combo.currentTextChanged.connect(self.symbol_selection_changed.emit)

        self.completer = QCompleter(available_symbols)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.symbol_combo.setCompleter(self.completer)

        entry_layout.addWidget(QLabel("Simbol:"), 1, 0)
        entry_layout.addWidget(self.symbol_combo, 1, 1)
        
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(TIMEFRAME_MAP.keys())
        entry_layout.addWidget(QLabel("Timeframe:"), 2, 0)
        entry_layout.addWidget(self.timeframe_combo, 2, 1)

        self.magic_input = QLineEdit(str(initial_magic))
        entry_layout.addWidget(QLabel("Magic Number:"), 3, 0)
        entry_layout.addWidget(self.magic_input, 3, 1)

        # --- Bagian Parameter Entri (Dinamis) ---
        self.entry_params_group = QGroupBox("Parameter Strategi Entri")
        self.entry_params_layout = QGridLayout(self.entry_params_group)
        self.main_layout.addWidget(self.entry_params_group)
        self.entry_parameter_widgets = {}

        # --- Bagian Pengaturan Smart Exit ---
        self.exit_group = QGroupBox("Pengaturan Smart Exit")
        self.exit_group.setCheckable(True)
        self.exit_group.setChecked(False)
        
        exit_main_layout = QVBoxLayout(self.exit_group)
        exit_selection_layout = QGridLayout()
        
        self.exit_strategy_combo = QComboBox()
        for display_name in self.exit_strategy_map.values():
            self.exit_strategy_combo.addItem(display_name)
        exit_selection_layout.addWidget(QLabel("Strategi Exit:"), 0, 0)
        exit_selection_layout.addWidget(self.exit_strategy_combo, 0, 1)
        
        self.exit_params_layout = QGridLayout()
        self.exit_parameter_widgets = {}

        exit_main_layout.addLayout(exit_selection_layout)
        exit_main_layout.addLayout(self.exit_params_layout)
        self.main_layout.addWidget(self.exit_group)
        self.main_layout.addStretch()

        # 4. HUBUNGKAN SINYAL
        self.strategy_combo.currentTextChanged.connect(self.on_entry_strategy_selected)
        self.exit_strategy_combo.currentTextChanged.connect(self.on_exit_strategy_selected)
        
        # 5. BANGUN UI AWAL
        self.on_entry_strategy_selected(self.strategy_combo.currentText())
        self.on_exit_strategy_selected(self.exit_strategy_combo.currentText())

    def update_available_symbols(self, all_symbols: list, used_symbols: set):
        """[VERSI FINAL] Memperbarui dropdown simbol dengan item yang bisa dinonaktifkan."""
        current_selection = self.symbol_combo.currentText()
        
        self.symbol_combo.blockSignals(True)
        self.symbol_combo.clear()

        available_for_this_tab = [s for s in all_symbols if s not in used_symbols]
        
        # Jika pilihan saat ini adalah salah satu yang valid, tambahkan ke daftar
        if current_selection and (current_selection in used_symbols):
            available_for_this_tab.insert(0, current_selection)

        # Isi combobox dan completer dengan daftar yang sudah difilter
        self.symbol_combo.addItems(sorted(available_for_this_tab))
        self.completer.model().setStringList(sorted(available_for_this_tab))
        
        self.symbol_combo.setCurrentText(current_selection)
        self.symbol_combo.blockSignals(False)

    def _load_parameters(self, strategy_map, subfolder):
        """Memuat kamus 'parameters' dari setiap kelas strategi."""
        params = {}
        for class_name in strategy_map.keys():
            try:
                module_name = camel_to_snake(class_name)
                module = importlib.import_module(f"Library.{subfolder}.{module_name}")
                StrategyClass = getattr(module, class_name)
                params[class_name] = getattr(StrategyClass, 'parameters', {})
            except (ImportError, AttributeError, ModuleNotFoundError) as e:
                print(f"Gagal memuat parameter untuk {class_name}: {e}")
                continue
        return params
    
    def on_entry_strategy_selected(self, strategy_display_name: str):
        selected_class_name = next((cn for cn, dn in self.entry_strategy_map.items() if dn == strategy_display_name), None)
        if selected_class_name:
            self._rebuild_parameter_ui(selected_class_name, 
                                       self.entry_strategy_params,
                                       self.entry_params_layout,
                                       self.entry_parameter_widgets)
            
    def on_exit_strategy_selected(self, strategy_display_name: str):
        selected_class_name = next((cn for cn, dn in self.exit_strategy_map.items() if dn == strategy_display_name), None)
        if selected_class_name:
            self._rebuild_parameter_ui(selected_class_name,
                                       self.exit_strategy_params,
                                       self.exit_params_layout,
                                       self.exit_parameter_widgets)

    def _rebuild_parameter_ui(self, class_name, params_map, layout, widget_dict):
        """Fungsi generik untuk membangun UI parameter dinamis."""
        for widget in widget_dict.values():
            widget.deleteLater()
        widget_dict.clear()
        
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        parameters = params_map.get(class_name, {})
        for i, (param_key, param_info) in enumerate(parameters.items()):
            label = QLabel(f"{param_info.get('display_name', param_key)}:")
            widget_type = param_info.get("type", "str")
            
            if widget_type == "int":
                widget = QSpinBox()
                widget.setRange(param_info.get("min", 0), param_info.get("max", 1000))
                widget.setValue(param_info.get("default", 0))
            elif widget_type == "float":
                widget = QDoubleSpinBox()
                widget.setRange(param_info.get("min", 0.0), param_info.get("max", 1000.0))
                widget.setSingleStep(param_info.get("step", 0.1))
                widget.setValue(param_info.get("default", 0.0))
            else:
                widget = QLineEdit(str(param_info.get("default", "")))
            
            layout.addWidget(label, i, 0)
            layout.addWidget(widget, i, 1)
            widget_dict[param_key] = widget

    def get_config(self) -> dict:
        """[FINAL] Membaca nilai dari semua widget, termasuk Smart Exit."""
        config_data = {
            "symbol": self.symbol_combo.currentText(),
            "timeframe": self.timeframe_combo.currentText(),
            "magic_number": self.magic_input.text()
        }
        
        # Ambil nama kelas strategi entri
        selected_entry_dn = self.strategy_combo.currentText()
        entry_cn = next((cn for cn, dn in self.entry_strategy_map.items() if dn == selected_entry_dn), None)
        if entry_cn: config_data["strategy_class"] = entry_cn
        
        # Ambil nilai dari parameter entri dinamis
        for key, widget in self.entry_parameter_widgets.items():
            config_data[key] = widget.value() if isinstance(widget, (QSpinBox, QDoubleSpinBox)) else widget.text()

        # Ambil data Smart Exit
        config_data['use_smart_exit'] = self.exit_group.isChecked()
        if config_data['use_smart_exit']:
            selected_exit_dn = self.exit_strategy_combo.currentText()
            exit_cn = next((cn for cn, dn in self.exit_strategy_map.items() if dn == selected_exit_dn), None)
            if exit_cn: config_data["exit_strategy_class"] = exit_cn

            for key, widget in self.exit_parameter_widgets.items():
                config_data[key] = widget.value() if isinstance(widget, (QSpinBox, QDoubleSpinBox)) else widget.text()

        # Tambahkan data integer MT5 & Magic Number
        config_data['timeframe_int'] = TIMEFRAME_MAP.get(config_data.get('timeframe'), mt5.TIMEFRAME_M1)
        try: config_data['magic_number'] = int(config_data.get('magic_number', 0))
        except (ValueError, TypeError): config_data['magic_number'] = 0
            
        return config_data

    def set_config(self, config: dict):
        """[FINAL] Mengisi semua widget dengan data, termasuk Smart Exit."""
        # Atur widget entri statis
        entry_cn = config.get("strategy_class")
        if entry_cn and entry_cn in self.entry_strategy_map:
            self.strategy_combo.setCurrentText(self.entry_strategy_map[entry_cn])
        
        self.symbol_combo.setCurrentText(config.get("symbol", ""))
        self.timeframe_combo.setCurrentText(config.get("timeframe", "M1"))
        self.magic_input.setText(str(config.get("magic_number", "")))
        
        # Atur nilai widget entri dinamis
        for key, widget in self.entry_parameter_widgets.items():
            if key in config:
                value = config[key]
                if isinstance(widget, QSpinBox): widget.setValue(int(float(value)))
                elif isinstance(widget, QDoubleSpinBox): widget.setValue(float(value))
                else: widget.setText(str(value))

        # Atur Smart Exit
        use_exit = config.get('use_smart_exit', False)
        self.exit_group.setChecked(use_exit)
        
        if use_exit:
            exit_cn = config.get("exit_strategy_class")
            if exit_cn and exit_cn in self.exit_strategy_map:
                self.exit_strategy_combo.setCurrentText(self.exit_strategy_map[exit_cn])
            
            # Atur nilai widget exit dinamis
            for key, widget in self.exit_parameter_widgets.items():
                if key in config:
                    value = config[key]
                    if isinstance(widget, QSpinBox): widget.setValue(int(float(value)))
                    elif isinstance(widget, QDoubleSpinBox): widget.setValue(float(value))
                    else: widget.setText(str(value))

# --- Jendela Utama Pengaturan Strategi ---
class SettingsWindow(QDialog):
    settings_changed = pyqtSignal(dict)
    log_message_generated = pyqtSignal(str)
    def __init__(self, symbols: list, account_number: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Pengaturan untuk Akun {account_number}") # Judul dinamis
        self.setWindowIcon(qta.icon('fa5s.cogs', color='white'))
        self.setGeometry(250, 250, 450, 400)
        
        self.available_symbols = symbols
        self.account_number = account_number
        self.base_magic_number = 12345

        layout = QVBoxLayout(self)
        self.main_tabs = QTabWidget()
        layout.addWidget(self.main_tabs)
        
        # Setup semua tab UI...
        self.account_manager_tab = AccountManagerTab()
        self.main_tabs.addTab(self.account_manager_tab, "Manajemen Akun")

        self.strategy_tabs = QTabWidget()
        self.strategy_tabs.setTabsClosable(True)
        self.strategy_tabs.tabCloseRequested.connect(self.remove_strategy_tab)
        self.main_tabs.addTab(self.strategy_tabs, "Strategi per Pair")
        
        self.btn_add_pair = QPushButton(qta.icon('fa5s.plus'), " Add Pair")
        self.btn_add_pair.clicked.connect(self.add_strategy_tab)
        self.strategy_tabs.setCornerWidget(self.btn_add_pair, Qt.Corner.TopLeftCorner)
        self.available_strategies = load_available_strategies()
        self.available_exit_strategies = load_available_exit_strategies()
        
        # Hanya panggil SATU fungsi load yang baru
        self.load_configs()
        self.initial_tm_config = self.get_tm_config()
        self.initial_strategy_configs = self.get_strategy_configs()
        self.account_manager_tab.config_changed.connect(self.on_settings_changed)

    def on_settings_changed(self):
        """Mengambil config TM saat ini dan memancarkannya."""
        current_tm_config = self.account_manager_tab.get_config()
        self.settings_changed.emit(current_tm_config)

    def add_strategy_tab(self, config: dict = None):
        new_magic = self.base_magic_number + self.strategy_tabs.count()
        # [PERBAIKAN] Teruskan juga daftar strategi exit
        new_tab = StrategyTab(self.available_symbols, new_magic, 
                            self.available_strategies, 
                            self.available_exit_strategies)
        new_tab.symbol_selection_changed.connect(self.on_any_symbol_changed)
        if config: new_tab.set_config(config)
        self.strategy_tabs.addTab(new_tab, f"Pair {self.strategy_tabs.count() + 1}")
        self.on_any_symbol_changed()

    def remove_strategy_tab(self, index: int):
        if self.strategy_tabs.count() > 1:
            self.strategy_tabs.removeTab(index)
        else:
            QMessageBox.warning(self, "Aksi Ditolak", "Setidaknya harus ada satu tab strategi.")
        self.on_any_symbol_changed()
    
    def on_any_symbol_changed(self):
        """Dipanggil setiap kali ada perubahan simbol di tab manapun."""
        all_symbols = self.available_symbols
        
        # Kumpulkan semua simbol yang sedang digunakan di semua tab
        used_symbols = set()
        for i in range(self.strategy_tabs.count()):
            tab = self.strategy_tabs.widget(i)
            selected_symbol = tab.symbol_combo.currentText()
            if selected_symbol:
                used_symbols.add(selected_symbol)

        # Beri tahu setiap tab untuk memperbarui daftarnya
        for i in range(self.strategy_tabs.count()):
            tab = self.strategy_tabs.widget(i)
            tab.update_available_symbols(all_symbols, used_symbols)
            
    def get_tm_config(self) -> dict:
        return self.account_manager_tab.get_config()

    def get_strategy_configs(self) -> list:
        return [self.strategy_tabs.widget(i).get_config() for i in range(self.strategy_tabs.count())]
    
    def update_account_info(self, acc_info):
        self.account_manager_tab.update_account_info(acc_info)

    def save_configs(self, show_popup=True):
        """Menyimpan semua konfigurasi ke satu file JSON per akun."""
        # Cek apakah folder 'configs' sudah ada, jika tidak, buat folder tersebut
        if not os.path.exists('configs'):
            os.makedirs('configs')
                
        config_path = f"configs/{self.account_number}.json"
        
        all_data = {
            'tm_config': self.get_tm_config(),
            'strategy_configs': self.get_strategy_configs()
        }

        try:
            with open(config_path, 'w') as f:
                json.dump(all_data, f, indent=4)

            log_msg = f"Pengaturan untuk akun {self.account_number} telah disimpan."
            self.log_message_generated.emit(log_msg)
            
            # [PENTING] Perbarui kondisi awal setelah menyimpan
            self.initial_tm_config = all_data['tm_config']
            self.initial_strategy_configs = all_data['strategy_configs']

            if show_popup:
                QMessageBox.information(self, "Berhasil", f"Pengaturan berhasil disimpan ke:\n{config_path}")
        except Exception as e:
            if show_popup:
                QMessageBox.critical(self, "Gagal", f"Gagal menyimpan pengaturan: {e}")

    def load_configs(self):
        """[VERSI BARU] Memuat konfigurasi dari file JSON spesifik per akun."""
        config_path = f"configs/{self.account_number}.json"
        if not os.path.exists(config_path):
            print(f"File konfigurasi {config_path} belum ada. Menampilkan tab default.")
            self.add_strategy_tab() # Tambahkan satu tab strategi kosong
            return

        try:
            with open(config_path, 'r') as f:
                saved_data = json.load(f)
            
            # Isi data untuk tab Trade Manager
            tm_config = saved_data.get('tm_config', {})
            self.account_manager_tab.set_config(tm_config)

            # Isi data untuk tab Strategi
            strategy_configs = saved_data.get('strategy_configs', [])
            # Hapus tab default yang mungkin sudah ada
            while self.strategy_tabs.count() > 0:
                self.strategy_tabs.removeTab(0)

            if not strategy_configs:
                self.add_strategy_tab() # Jika kosong, tambahkan satu tab default
            else:
                for config in strategy_configs:
                    self.add_strategy_tab(config=config)

            print(f"Pengaturan dari {config_path} berhasil dimuat.")

        except Exception as e:
            QMessageBox.warning(self, "Gagal Memuat", f"Gagal memuat pengaturan dari file: {e}")
            self.add_strategy_tab()

    def closeEvent(self, event):
        """[VERSI BARU] Cek perubahan sebelum menutup."""
        # Ambil konfigurasi saat ini
        current_tm_config = self.get_tm_config()
        current_strategy_configs = self.get_strategy_configs()
        
        # Bandingkan dengan konfigurasi awal
        has_changes = (current_tm_config != self.initial_tm_config or 
                    current_strategy_configs != self.initial_strategy_configs)

        if has_changes:
            # Jika ada perubahan, tampilkan dialog konfirmasi
            reply = QMessageBox.question(self, 'Simpan Perubahan?',
                                        "Anda memiliki perubahan yang belum disimpan. Apakah Anda ingin menyimpannya?",
                                        QMessageBox.StandardButton.Save | 
                                        QMessageBox.StandardButton.Discard | 
                                        QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Save:
                self.save_configs(show_popup=False) # Simpan tanpa popup
                event.accept() # Tutup jendela
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept() # Tutup jendela tanpa menyimpan
            else: # reply == QMessageBox.StandardButton.Cancel
                event.ignore() # Jangan tutup jendela
        else:
            # Jika tidak ada perubahan, langsung tutup saja
            event.accept()