# Library/utils/path_finder.py

import os
import sys
import winreg
import json

from PyQt6.QtCore import QObject, pyqtSignal

class DeepScanner(QObject):
    """
    Kelas yang membungkus logika deep scan agar bisa memancarkan sinyal
    untuk update UI (progress bar dan label).
    """
    # Sinyal yang akan membawa path direktori yang sedang di-scan
    directory_changed = pyqtSignal(str)
    # Sinyal yang membawa daftar path yang ditemukan setelah selesai
    scan_finished = pyqtSignal(set)

    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        """Memulai proses deep scan."""
        found_paths = set()
        target_file = "terminal64.exe"
        
        # Tentukan lokasi pencarian
        search_locations = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        ]
        # Tambahkan drive lain jika ada (contoh: D:, E:, dst.)
        for letter in 'DEFGHIJKLMNOPQRSTUVWXYZ':
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                search_locations.append(drive)

        for location in search_locations:
            if not self.is_running:
                break
            # Gunakan os.walk untuk menjelajahi direktori
            for root, dirs, files in os.walk(location):
                if not self.is_running:
                    break
                # Pancarkan sinyal direktori saat ini untuk update UI
                self.directory_changed.emit(root)

                if target_file in files:
                    path = os.path.join(root, target_file)
                    found_paths.add(path)
                
                # Optimasi agar tidak mencari di folder sistem yang tidak relevan
                dirs[:] = [d for d in dirs if d.lower() not in [
                    'windows', 'python', '$recycle.bin', 'appdata', 
                    'programdata', 'system volume information'
                ]]
        
        # Pancarkan sinyal selesai dengan hasil yang ditemukan
        self.scan_finished.emit(found_paths)

    def stop(self):
        """Menghentikan proses scan."""
        self.is_running = False

def get_data_file_path(robot_root_path: str, filename: str) -> str:
    return os.path.join(robot_root_path, filename)

def save_accounts_data(robot_root_path: str, data: dict):
    file_path = get_data_file_path(robot_root_path, "accounts.json")
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Gagal menyimpan accounts.json: {e}")

def load_accounts_data(robot_root_path: str) -> dict:
    file_path = get_data_file_path(robot_root_path, "accounts.json")
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_known_paths(robot_root_path: str, paths: set):
    file_path = get_data_file_path(robot_root_path, "known_paths.json")
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(list(paths), f, indent=4)
    except Exception as e:
        print(f"Gagal menyimpan known_paths.json: {e}")

def load_known_paths(robot_root_path: str) -> set:
    file_path = get_data_file_path(robot_root_path, "known_paths.json")
    if not os.path.exists(file_path):
        return set()
    try:
        with open(file_path, "r") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, FileNotFoundError):
        return set()

def scan_for_metatrader_enhanced():
    found_paths = set()
    keys_to_check = [
        (winreg.HKEY_CURRENT_USER, r"Software\MetaQuotes\Terminal"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\MetaQuotes\Terminal"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\MetaQuotes\Terminal")
    ]
    for hkey, key_path in keys_to_check:
        try:
            with winreg.OpenKey(hkey, key_path, 0, winreg.KEY_READ) as main_key:
                for i in range(winreg.QueryInfoKey(main_key)[0]):
                    sub_key_name = winreg.EnumKey(main_key, i)
                    try:
                        with winreg.OpenKey(main_key, sub_key_name) as sub_key:
                            exe_path, _ = winreg.QueryValueEx(sub_key, "ExePath")
                            if exe_path and "terminal64.exe" in exe_path and os.path.exists(exe_path):
                                found_paths.add(exe_path)
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            continue
    return found_paths

def find_by_smart_search():
    found_paths = set()
    target_file = "terminal64.exe"
    keywords = ["metatrader", "mt5"]
    base_dirs = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    ]
    for base_dir in base_dirs:
        if not os.path.isdir(base_dir): continue
        try:
            for item_name in os.listdir(base_dir):
                if any(keyword in item_name.lower() for keyword in keywords):
                    potential_path = os.path.join(base_dir, item_name, target_file)
                    if os.path.exists(potential_path):
                        found_paths.add(potential_path)
        except (FileNotFoundError, PermissionError):
            continue
    return found_paths
