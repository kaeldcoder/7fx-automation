import json
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QTabWidget, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QDoubleSpinBox, 
                             QSpinBox, QMessageBox, QCompleter, QDialog, QCheckBox, QTimeEdit, QGroupBox, QAbstractSpinBox, QStackedLayout, QScrollArea)
from PyQt6.QtCore import Qt, QTime, pyqtSignal
import qtawesome as qta
import MetaTrader5 as mt5
import pytz
import importlib
import inspect
import re

from custom_dialogs import StyledDialog
from PyQt6.QtWidgets import QDialogButtonBox

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
        main_layout.setContentsMargins(15, 15, 15, 15) # Beri padding
        main_layout.setSpacing(20)

        # --- Management Settings ---
        settings_group = QGroupBox(self.tr("Management Settings"))
        layout = QVBoxLayout(settings_group)
        
        self.widgets = {}
        # Setiap baris sekarang adalah QHBoxLayout di dalam QVBoxLayout
        layout.addLayout(self._create_dynamic_target_widget(self.tr("Session Profit Target:"), "profit_target"))
        layout.addLayout(self._create_dynamic_target_widget(self.tr("Session Loss Limit:"), "loss_target"))
        layout.addLayout(self._create_dynamic_target_widget(self.tr("Absolute Equity Stop:"), "absolute_equity_stop", has_percent=False)) # Absolute stop tidak perlu persen
        layout.addLayout(self._create_labeled_widget(self.tr("Drawdown Mode:"), QComboBox(), "drawdown_mode", ["peak_equity", "initial_balance"]))
        
        # --- Gradual & Consecutive Stop ---
        self.widgets["use_gradual_stop"] = QCheckBox(self.tr("Gradual Stop"))
        self.widgets["gradual_stop_percent"] = QDoubleSpinBox()
        layout.addLayout(self._create_checkbox_spinbox_layout(self.widgets["use_gradual_stop"], self.widgets["gradual_stop_percent"]))
        
        self.widgets["use_consecutive_loss_stop"] = QCheckBox(self.tr("Consecutive Loss Stop"))
        self.widgets["max_consecutive_losses"] = QSpinBox()
        layout.addLayout(self._create_checkbox_spinbox_layout(self.widgets["use_consecutive_loss_stop"], self.widgets["max_consecutive_losses"]))

        # --- Timezone & Cooldown ---
        common_timezones = sorted([tz for tz in pytz.common_timezones if any(c in tz for c in ["Asia", "Etc", "UTC", "Europe", "America"])])
        layout.addLayout(self._create_labeled_widget(self.tr("Timezone:"), QComboBox(), "timezone", common_timezones))
        layout.addLayout(self._create_labeled_widget(self.tr("Cooldown Mode:"), QComboBox(), "cooldown_mode", ["next_day_at", "duration", "next_candle"]))
        
        self.widgets["cooldown_mode"].currentTextChanged.connect(self._update_cooldown_ui)
        self._update_cooldown_ui(self.widgets["cooldown_mode"].currentText())

        main_layout.addWidget(settings_group)

        # --- Order Control Settings ---
        trade_control_group = QGroupBox(self.tr("Order Control Settings"))
        trade_layout = QGridLayout(trade_control_group)
        trade_layout.setColumnStretch(1, 1)
        trade_layout.setHorizontalSpacing(15); trade_layout.setVerticalSpacing(10)

        trade_layout.addWidget(QLabel(self.tr("Max Concurrent Trades:")), 0, 0)
        max_trades_spinbox = QSpinBox(); max_trades_spinbox.setRange(1, 100)
        self.widgets["max_concurrent_trades"] = max_trades_spinbox
        trade_layout.addWidget(self._create_spinbox_with_buttons(max_trades_spinbox), 0, 1)
        
        trade_layout.addWidget(QLabel(self.tr("Order Cooldown (seconds):")), 1, 0)
        cooldown_spinbox = QDoubleSpinBox(); cooldown_spinbox.setRange(0.1, 60.0); cooldown_spinbox.setSingleStep(0.1)
        self.widgets["order_cooldown_seconds"] = cooldown_spinbox
        trade_layout.addWidget(self._create_spinbox_with_buttons(cooldown_spinbox), 1, 1)

        main_layout.addWidget(trade_control_group)
        main_layout.addStretch() # Tambah stretch agar semua grup merapat ke atas

        for widget in self.widgets.values():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.valueChanged.connect(self.config_changed.emit)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self.config_changed.emit)
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self.config_changed.emit)
        
    def _create_dynamic_target_widget(self, label_text, key, has_percent=True):
        row_layout = QHBoxLayout()
        label = QLabel(label_text); label.setFixedWidth(160)
        row_layout.addWidget(label)
        
        spinbox = QDoubleSpinBox(); spinbox.setRange(0, 1000000)
        self.widgets[f"{key}_value"] = spinbox
        
        type_combo = QComboBox()
        options = ["Amount ($)"]
        if has_percent: options.append("Percent (%)")
        type_combo.addItems(options)
        self.widgets[f"{key}_type"] = type_combo

        # Gunakan helper baru
        spin_container = self._create_spinbox_with_buttons(spinbox)
        
        row_layout.addWidget(spin_container)
        row_layout.addWidget(type_combo)
        return row_layout

    def _create_labeled_widget(self, label_text, widget, key, items=None):
        """Membuat layout baris untuk Label dan Widget."""
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(160)
        row_layout.addWidget(label)
        
        self.widgets[key] = widget
        if items and isinstance(widget, QComboBox):
            widget.addItems(items)

        # [PERBAIKAN] Pindahkan logika cooldown detail ke sini
        if key == "cooldown_mode":
            self.cooldown_details_container = QWidget()
            details_layout = QHBoxLayout(self.cooldown_details_container)
            details_layout.setContentsMargins(0,0,0,0)
            self._create_cooldown_details_widgets(details_layout) # Kirim layout-nya
            
            stacked_layout = QVBoxLayout()
            stacked_layout.setContentsMargins(0,0,0,0)
            stacked_layout.addWidget(widget)
            stacked_layout.addWidget(self.cooldown_details_container)
            row_layout.addLayout(stacked_layout)
        else:
            row_layout.addWidget(widget)
            
        return row_layout
    
    @staticmethod
    def _create_spinbox_with_buttons(spinbox_widget):
        """Membungkus spinbox dengan tombol panah kustom."""
        spin_container = QWidget()
        spin_container.setMinimumHeight(40)
        spin_layout = QHBoxLayout(spin_container)
        spin_layout.setContentsMargins(0,0,0,0)
        spin_layout.setSpacing(1)
        
        spinbox_widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin_layout.addWidget(spinbox_widget)

        up_button = QPushButton("↑")
        down_button = QPushButton("↓")
        up_button.setObjectName("SpinBoxUpButton")
        down_button.setObjectName("SpinBoxDownButton")
        up_button.setFixedSize(22, 19)
        down_button.setFixedSize(22, 19)
        up_button.clicked.connect(spinbox_widget.stepUp)
        down_button.clicked.connect(spinbox_widget.stepDown)

        button_vbox = QVBoxLayout()
        button_vbox.setContentsMargins(0,0,0,0)
        button_vbox.setSpacing(1)
        button_vbox.addWidget(up_button)
        button_vbox.addWidget(down_button)
        spin_layout.addLayout(button_vbox)
        
        # Simpan referensi tombol untuk menonaktifkannya nanti
        spinbox_widget.custom_buttons = [up_button, down_button]

        return spin_container

    def _create_checkbox_spinbox_layout(self, checkbox, spinbox):
        row_layout = QHBoxLayout()
        checkbox.setFixedWidth(160)
        checkbox.setMinimumHeight(30)
        row_layout.addWidget(checkbox)
        
        # Gunakan helper baru
        spin_container = self._create_spinbox_with_buttons(spinbox)
        row_layout.addWidget(spin_container)
        
        checkbox.toggled.connect(spinbox.setEnabled)
        # Hubungkan juga ke tombol kustom
        for btn in spinbox.custom_buttons:
            checkbox.toggled.connect(btn.setEnabled)
            btn.setEnabled(checkbox.isChecked())
            
        spinbox.setEnabled(checkbox.isChecked())
        return row_layout

    def _create_cooldown_details_widgets(self, layout):
        self.cooldown_details_stack = QStackedLayout()

        # --- Duration ---
        self.widgets["cooldown_duration_hours"] = QSpinBox(); self.widgets["cooldown_duration_minutes"] = QSpinBox()
        self.duration_container = self._create_cooldown_duration_ui()
        
        # --- Next Day At (BARU) ---
        self.widgets["cooldown_time_hour"] = QComboBox()
        self.widgets["cooldown_time_minute"] = QComboBox()
        self.widgets["cooldown_time_ampm"] = QComboBox()
        self.next_day_container = self._create_cooldown_time_ui()

        # --- Next Candle ---
        timeframe_map_rev = {v: k for k, v in TIMEFRAME_MAP.items()}
        self.widgets["cooldown_next_candle_tf"] = QComboBox()
        self.widgets["cooldown_next_candle_tf"].addItems(timeframe_map_rev.values())
        self.next_candle_container = self._create_cooldown_tf_ui()

        self.cooldown_details_stack.addWidget(self.next_day_container) # index 0
        self.cooldown_details_stack.addWidget(self.duration_container) # index 1
        self.cooldown_details_stack.addWidget(self.next_candle_container) # index 2
        
        layout.addLayout(self.cooldown_details_stack)

    def _create_cooldown_duration_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel(self.tr("└─ Details:"))); layout.addSpacing(5)
        
        # Terapkan helper ke SpinBox Jam
        h_spinbox = self.widgets["cooldown_duration_hours"]
        layout.addWidget(self._create_spinbox_with_buttons(h_spinbox))
        layout.addWidget(QLabel(self.tr("H")))
        layout.addSpacing(10)

        # Terapkan helper ke SpinBox Menit
        m_spinbox = self.widgets["cooldown_duration_minutes"]
        layout.addWidget(self._create_spinbox_with_buttons(m_spinbox))
        layout.addWidget(QLabel(self.tr("M")))

        layout.addStretch()
        container = QWidget(); container.setLayout(layout)
        return container

    def _create_cooldown_time_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel(self.tr("└─ Time:"))); layout.addSpacing(5)
        
        # Isi pilihan untuk Jam, Menit, AM/PM
        self.widgets["cooldown_time_hour"].addItems([f"{h:02d}" for h in range(1, 13)])
        self.widgets["cooldown_time_minute"].addItems([f"{m:02d}" for m in range(0, 60, 5)]) # Kelipatan 5
        self.widgets["cooldown_time_ampm"].addItems(["AM", "PM"])

        # Atur ukuran agar proporsional
        self.widgets["cooldown_time_hour"].setFixedWidth(70)
        self.widgets["cooldown_time_minute"].setFixedWidth(70)
        self.widgets["cooldown_time_ampm"].setFixedWidth(70)

        layout.addWidget(self.widgets["cooldown_time_hour"])
        layout.addWidget(self.widgets["cooldown_time_minute"])
        layout.addWidget(self.widgets["cooldown_time_ampm"])
        layout.addStretch()
        
        container = QWidget(); container.setLayout(layout)
        return container

    def _create_cooldown_tf_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel(self.tr("└─ TF:"))); layout.addSpacing(5)
        
        tf_combo = self.widgets["cooldown_next_candle_tf"]
        tf_combo.setMinimumWidth(120) # Perbesar kotak
        layout.addWidget(tf_combo)
        
        layout.addStretch()
        container = QWidget(); container.setLayout(layout)
        return container

    def _update_cooldown_ui(self, mode):
        if mode == 'next_day_at':
            self.cooldown_details_stack.setCurrentIndex(0)
        elif mode == 'duration':
            self.cooldown_details_stack.setCurrentIndex(1)
        elif mode == 'next_candle':
            self.cooldown_details_stack.setCurrentIndex(2)

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
            type_text = "percent" if self.widgets[f"{key}_type"].currentIndex() == 1 else "amount"
            config[key] = {
                "value": self.widgets[f"{key}_value"].value(),
                "type": type_text
            }
        
        # Susun config cooldown
        mode = config.get("cooldown_mode", "duration")
        cooldown_details = {"mode": mode}
        if mode == 'duration':
            cooldown_details['hours'] = self.widgets["cooldown_duration_hours"].value()
            cooldown_details['minutes'] = self.widgets["cooldown_duration_minutes"].value()
        elif mode == 'next_day_at':
            # [DIUBAH] Baca dari 3 ComboBox dan konversi ke format HH:mm (24 jam)
            hour = int(self.widgets["cooldown_time_hour"].currentText())
            minute = int(self.widgets["cooldown_time_minute"].currentText())
            ampm = self.widgets["cooldown_time_ampm"].currentText()
            if ampm == "PM" and hour != 12: hour += 12
            if ampm == "AM" and hour == 12: hour = 0 # Tengah malam adalah jam 00
            cooldown_details['time'] = f"{hour:02d}:{minute:02d}"
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
                type_text = self.tr("Percent (%)") if config_data[key].get("type") == "percent" else self.tr("Amount ($)")
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
                # [DIUBAH] Ambil format HH:mm dan konversi ke 3 ComboBox
                time_24h_str = cooldown_cfg.get('time', '08:00')
                time_obj = QTime.fromString(time_24h_str, "HH:mm")
                hour_12h = int(time_obj.toString("hh"))
                minute = int(time_obj.toString("mm"))
                ampm = "AM" if time_obj.hour() < 12 else "PM"
                self.widgets['cooldown_time_hour'].setCurrentText(f"{hour_12h:02d}")
                self.widgets['cooldown_time_minute'].setCurrentText(f"{minute:02d}")
                self.widgets['cooldown_time_ampm'].setCurrentText(ampm)
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
        self.entry_strategy_map = entry_strategy_map
        self.exit_strategy_map = exit_strategy_map
        self.entry_strategy_params = self._load_parameters(entry_strategy_map, "strategies")
        self.exit_strategy_params = self._load_parameters(exit_strategy_map, "exit_strategies")

        self.entry_param_rows = {}
        self.exit_param_rows = {}

        # [BARU] Buat QScrollArea sebagai dasar
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("BubbleScrollArea") # Gunakan style scrollbar yang sudah ada

        # [BARU] Buat widget kontainer untuk menampung semua konten
        content_container = QWidget()
        scroll_area.setWidget(content_container)

        # [DIUBAH] Layout utama sekarang diletakkan di dalam kontainer, bukan di self
        self.main_layout = QVBoxLayout(content_container)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(20)

        # Buat layout untuk window ini, yang hanya akan berisi scroll area
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0,0,0,0)
        window_layout.addWidget(scroll_area)

        # --- Sisa dari UI dibuat seperti biasa dan ditambahkan ke self.main_layout ---
        entry_group = QGroupBox(self.tr("Entry Settings"))
        entry_layout = QGridLayout(entry_group)
        self.main_layout.addWidget(entry_group)

        # Widget statis
        self.strategy_combo = QComboBox()
        for display_name in self.entry_strategy_map.values():
            self.strategy_combo.addItem(display_name)
        entry_layout.addWidget(QLabel(self.tr("Entry Strategy:")), 0, 0)
        entry_layout.addWidget(self.strategy_combo, 0, 1)

        self.symbol_combo = QComboBox()
        self.symbol_combo.setEditable(True)
        self.symbol_combo.currentTextChanged.connect(self.symbol_selection_changed.emit)

        self.completer = QCompleter(available_symbols)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.symbol_combo.setCompleter(self.completer)
        entry_layout.addWidget(QLabel(self.tr("Symbol:")), 1, 0)
        entry_layout.addWidget(self.symbol_combo, 1, 1)
        
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(TIMEFRAME_MAP.keys())
        entry_layout.addWidget(QLabel(self.tr("Timeframe:")), 2, 0)
        entry_layout.addWidget(self.timeframe_combo, 2, 1)

        self.magic_input = QLineEdit(str(initial_magic))
        self.magic_input.setObjectName("MagicNumberInput")
        entry_layout.addWidget(QLabel(self.tr("Magic Number:")), 3, 0)
        entry_layout.addWidget(self.magic_input, 3, 1)

        # --- Bagian Parameter Entri (Dinamis) ---
        self.entry_params_group = QGroupBox(self.tr("Entry Strategy Parameters"))
        self.entry_params_layout = QGridLayout(self.entry_params_group)
        self.main_layout.addWidget(self.entry_params_group)
        self.entry_parameter_widgets = {}

        # --- Bagian Pengaturan Smart Exit ---
        self.exit_group = QGroupBox(self.tr("Smart Exit Settings"))
        self.exit_group.setCheckable(True)
        self.exit_group.setChecked(False)
        
        exit_main_layout = QVBoxLayout(self.exit_group)
        exit_selection_layout = QGridLayout()
        
        self.exit_strategy_combo = QComboBox()
        for display_name in self.exit_strategy_map.values():
            self.exit_strategy_combo.addItem(display_name)
        exit_selection_layout.addWidget(QLabel(self.tr("Exit Strategy:")), 0, 0)
        exit_selection_layout.addWidget(self.exit_strategy_combo, 0, 1)
        
        self.exit_params_layout = QGridLayout()
        self.exit_parameter_widgets = {}

        exit_main_layout.addLayout(exit_selection_layout)
        exit_main_layout.addLayout(self.exit_params_layout)
        self.main_layout.addWidget(self.exit_group)
        self.main_layout.addStretch()

        # Hubungkan sinyal
        self.strategy_combo.currentTextChanged.connect(self.on_entry_strategy_selected)
        self.exit_strategy_combo.currentTextChanged.connect(self.on_exit_strategy_selected)
        
        # Bangun UI Awal
        self.on_entry_strategy_selected(self.strategy_combo.currentText())
        self.on_exit_strategy_selected(self.exit_strategy_combo.currentText())

    def update_available_symbols(self, all_symbols: list, used_symbols: set):
        current_selection = self.symbol_combo.currentText()
        self.symbol_combo.blockSignals(True)
        self.symbol_combo.clear()
        available_for_this_tab = [s for s in all_symbols if s not in used_symbols]
        if current_selection and (current_selection in used_symbols):
            available_for_this_tab.insert(0, current_selection)
        self.symbol_combo.addItems(sorted(available_for_this_tab))
        self.completer.model().setStringList(sorted(available_for_this_tab))
        self.symbol_combo.setCurrentText(current_selection)
        self.symbol_combo.blockSignals(False)

    def _load_parameters(self, strategy_map, subfolder):
        params = {}
        for class_name in strategy_map.keys():
            try:
                module_name = camel_to_snake(class_name)
                module = importlib.import_module(f"Library.{subfolder}.{module_name}")
                StrategyClass = getattr(module, class_name)
                params[class_name] = getattr(StrategyClass, 'parameters', {})
            except (ImportError, AttributeError, ModuleNotFoundError) as e:
                print(self.tr("Failed to load parameters for {0}: {1}").format(class_name, e))
                continue
        return params
    
    def on_entry_strategy_selected(self, strategy_display_name: str):
        selected_class_name = next((cn for cn, dn in self.entry_strategy_map.items() if dn == strategy_display_name), None)
        if selected_class_name:
            self._rebuild_parameter_ui(selected_class_name, 
                                       self.entry_strategy_params,
                                       self.entry_params_layout,
                                       self.entry_parameter_widgets,
                                       self.entry_param_rows)
            
    def on_exit_strategy_selected(self, strategy_display_name: str):
        selected_class_name = next((cn for cn, dn in self.exit_strategy_map.items() if dn == strategy_display_name), None)
        if selected_class_name:
            self._rebuild_parameter_ui(selected_class_name,
                                       self.exit_strategy_params,
                                       self.exit_params_layout,
                                       self.exit_parameter_widgets,
                                       self.exit_param_rows)

    def _rebuild_parameter_ui(self, class_name, params_map, layout, widget_dict, row_dict):
        """Fungsi generik untuk membangun UI parameter dinamis."""
        # [PERBAIKAN FINAL] Hancurkan semua widget di dalam layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        widget_dict.clear()
        row_dict.clear()

        # Buat ulang UI parameter
        parameters = params_map.get(class_name, {})
        for i, (param_key, param_info) in enumerate(parameters.items()):
            label = QLabel(f"{param_info.get('display_name', param_key)}:")
            widget_type = param_info.get("type", "str")
            
            if widget_type == "int":
                widget = QSpinBox()
                widget.setRange(param_info.get("min", 0), param_info.get("max", 1000))
                final_widget = AccountManagerTab._create_spinbox_with_buttons(widget)
            elif widget_type == "float":
                widget = QDoubleSpinBox()
                widget.setRange(param_info.get("min", 0.0), param_info.get("max", 1000.0))
                widget.setSingleStep(param_info.get("step", 0.1))
                final_widget = AccountManagerTab._create_spinbox_with_buttons(widget)
            elif widget_type == "option": # Tipe dropdown baru
                widget = QComboBox()
                widget.addItems(param_info.get("options", []))
                final_widget = widget
            else:
                widget = QLineEdit()
                widget.setObjectName("MagicNumberInput")
                final_widget = widget
            
            layout.addWidget(label, i, 0)
            layout.addWidget(final_widget, i, 1)
            widget_dict[param_key] = widget
            row_dict[param_key] = (label, final_widget)

        for param_key, param_info in parameters.items():
            if "condition" in param_info:
                controller_key, op, expected_value = param_info['condition']
                
                if op == '==' and controller_key in widget_dict:
                    controller_widget = widget_dict[controller_key]
                    dependent_label, dependent_widget = row_dict[param_key]

                    # Gunakan lambda dengan argumen default untuk menangkap variabel saat ini
                    handler = lambda text, lbl=dependent_label, wgt=dependent_widget, val=expected_value: (
                        lbl.setVisible(text == val),
                        wgt.setVisible(text == val)
                    )
                    
                    if isinstance(controller_widget, QComboBox):
                        controller_widget.currentTextChanged.connect(handler)
                        # Panggil handler sekali untuk mengatur visibilitas awal
                        handler(controller_widget.currentText())

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
            _label, container = self.entry_param_rows[key]
            if container.isVisible():
                if isinstance(widget, (QSpinBox, QDoubleSpinBox)): config_data[key] = widget.value()
                elif isinstance(widget, QComboBox): config_data[key] = widget.currentText()
                else: config_data[key] = widget.text()

        # Ambil data Smart Exit
        config_data['use_smart_exit'] = self.exit_group.isChecked()
        if config_data['use_smart_exit']:
            selected_exit_dn = self.exit_strategy_combo.currentText()
            exit_cn = next((cn for cn, dn in self.exit_strategy_map.items() if dn == selected_exit_dn), None)
            if exit_cn: config_data["exit_strategy_class"] = exit_cn

            for key, widget in self.exit_parameter_widgets.items():
                _label, container = self.exit_param_rows[key]
                if container.isVisible():
                    if isinstance(widget, (QSpinBox, QDoubleSpinBox)): config_data[key] = widget.value()
                    elif isinstance(widget, QComboBox): config_data[key] = widget.currentText()
                    else: config_data[key] = widget.text()

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
                elif isinstance(widget, QComboBox): widget.setCurrentText(str(value))
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
                    elif isinstance(widget, QComboBox): widget.setCurrentText(str(value))
                    else: widget.setText(str(value))

# --- Jendela Utama Pengaturan Strategi ---
class SettingsWindow(StyledDialog):
    settings_changed = pyqtSignal(dict)
    log_message_generated = pyqtSignal(str)
    def __init__(self, symbols: list, account_number: int, parent=None):
        # [DIUBAH] Panggil init dari StyledDialog dengan judul
        super().__init__(title=self.tr("Settings for Account {0}").format(account_number), parent=parent)
        self.setMinimumSize(700, 850) # Beri ukuran minimum
        
        self.available_symbols = symbols
        self.account_number = account_number
        self.base_magic_number = 12345

        # --- Buat UI seperti biasa ---
        self.main_tabs = QTabWidget()
        
        self.account_manager_tab = AccountManagerTab()
        self.main_tabs.addTab(self.account_manager_tab, self.tr("Account Management"))

        self.strategy_tabs = QTabWidget()
        self.strategy_tabs.setObjectName("StrategyPairTabs")
        self.strategy_tabs.setTabsClosable(True)
        self.strategy_tabs.tabCloseRequested.connect(self.remove_strategy_tab)
        self.main_tabs.addTab(self.strategy_tabs, self.tr("Strategy per Pair"))
        
        self.btn_add_pair = QPushButton(qta.icon('fa5s.plus'), self.tr(" Add Pair"))
        self.btn_add_pair.setObjectName("AccountActionButton") # Beri style pada tombol
        self.btn_add_pair.clicked.connect(self.add_strategy_tab)
        self.strategy_tabs.setCornerWidget(self.btn_add_pair, Qt.Corner.TopLeftCorner)
        self.available_strategies = load_available_strategies()
        self.available_exit_strategies = load_available_exit_strategies()
        
        # [DIUBAH] Masukkan semua elemen UI ke dalam content_layout dari StyledDialog
        self.content_layout.addWidget(self.main_tabs)

        # [BARU] Tambahkan tombol Save dan Cancel di bagian bawah
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        # Beri style pada tombol
        btn_save = button_box.button(QDialogButtonBox.StandardButton.Save)
        btn_save.setObjectName("DialogButton")
        btn_save.setProperty("class", "affirmative")
        btn_cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setObjectName("DialogButton")

        button_box.accepted.connect(self.accept_and_save)
        button_box.rejected.connect(self.reject)
        
        self.content_layout.addSpacing(15)
        self.content_layout.addWidget(button_box)

        # Muat konfigurasi
        self.load_configs()
        self.initial_tm_config = self.get_tm_config()
        self.initial_strategy_configs = self.get_strategy_configs()
        self.account_manager_tab.config_changed.connect(self.on_settings_changed)
    
    def accept_and_save(self):
        """Simpan konfigurasi dan tutup dialog."""
        self.save_configs(show_popup=False) # Simpan tanpa memunculkan popup
        self.accept()

    def on_settings_changed(self):
        """Mengambil config TM saat ini dan memancarkannya."""
        current_tm_config = self.account_manager_tab.get_config()
        self.settings_changed.emit(current_tm_config)

    def add_strategy_tab(self, config: dict = None):
        # --- [LOGIKA BARU] untuk Magic Number Unik ---
        max_magic = self.base_magic_number - 1 # Mulai dari angka sebelum basis

        # Loop melalui semua tab yang ada untuk menemukan magic number tertinggi
        for i in range(self.strategy_tabs.count()):
            tab = self.strategy_tabs.widget(i)
            try:
                # Ambil magic number dari input field di setiap tab
                current_magic = int(tab.magic_input.text())
                if current_magic > max_magic:
                    max_magic = current_magic
            except (ValueError, AttributeError):
                # Abaikan jika input kosong atau bukan angka
                continue

        # Magic number baru adalah yang tertinggi ditemukan + 1
        new_magic = max_magic + 1
        # --- [AKHIR LOGIKA BARU] ---

        # Sisa dari fungsi ini tidak berubah
        new_tab = StrategyTab(self.available_symbols, new_magic,
                            self.available_strategies,
                            self.available_exit_strategies)
        new_tab.symbol_selection_changed.connect(self.on_any_symbol_changed)
        
        if config:
            new_tab.set_config(config)
            
        self.strategy_tabs.addTab(new_tab, self.tr("Pair {0}").format(self.strategy_tabs.count() + 1))
        self.on_any_symbol_changed()

    def remove_strategy_tab(self, index: int):
        if self.strategy_tabs.count() > 1:
            self.strategy_tabs.removeTab(index)
        else:
            QMessageBox.warning(self, self.tr("Action Denied"), self.tr("There must be at least one strategy tab."))
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

            log_msg = self.tr("Settings for account {0} have been saved.").format(self.account_number)
            self.log_message_generated.emit(log_msg)
            
            # [PENTING] Perbarui kondisi awal setelah menyimpan
            self.initial_tm_config = all_data['tm_config']
            self.initial_strategy_configs = all_data['strategy_configs']

            if show_popup:
                QMessageBox.information(self, self.tr("Success"), self.tr("Settings successfully saved to:\n{0}").format(config_path))
        except Exception as e:
            if show_popup:
                QMessageBox.critical(self, self.tr("Failed"), self.tr("Failed to save settings: {0}").format(e))

    def load_configs(self):
        """[VERSI BARU] Memuat konfigurasi dari file JSON spesifik per akun."""
        config_path = f"configs/{self.account_number}.json"
        if not os.path.exists(config_path):
            print(self.tr("Configuration file {0} does not exist yet. Displaying default tab.").format(config_path))
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

            print(self.tr("Settings from {0} successfully loaded.").format(config_path))

        except Exception as e:
            QMessageBox.warning(self, self.tr("Load Failed"), self.tr("Failed to load settings from file: {0}").format(e))
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
            reply = QMessageBox.question(self, self.tr('Save Changes?'),
                                        self.tr("You have unsaved changes. Would you like to save them?"),
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