import os
import json

def save_json(file_path: str, data: dict | list):
    """Menyimpan data (dictionary atau list) ke sebuah file JSON."""
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Gagal menyimpan file {file_path}: {e}")
        return False

def load_json(file_path: str, default_type: str = 'dict'):
    """Memuat data dari file JSON. Mengembalikan dict atau list kosong jika gagal."""
    if not os.path.exists(file_path):
        return {} if default_type == 'dict' else []
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {} if default_type == 'dict' else []