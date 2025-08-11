# generate_translations.py

import os
import subprocess # <-- Impor modul subprocess

def find_py_files(directory='.'):
    """Mencari semua file .py secara rekursif."""
    file_list = []
    for root, _, files in os.walk(directory):
        # Abaikan folder virtual environment
        if 'venv' in root or '__pycache__' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                relative_path = os.path.relpath(os.path.join(root, file))
                file_list.append(relative_path)
    return file_list

def main():
    """Skrip utama untuk membuat atau memperbarui file terjemahan."""
    print("Memulai proses pembuatan file terjemahan...")
    
    languages = ['en_US', 'id_ID']
    translations_dir = 'translations'
    os.makedirs(translations_dir, exist_ok=True)
    
    python_files = find_py_files()
    
    for lang in languages:
        ts_file = os.path.join(translations_dir, f'{lang}.ts')
        
        # --- PERUBAHAN INTI DI SINI ---
        # Bangun perintah sebagai list of strings
        command = ['pylupdate6', '-ts', ts_file] + python_files
        
        print(f"\nMenjalankan untuk bahasa: {lang}")
        
        try:
            # Jalankan perintah menggunakan subprocess
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            print(f"File '{ts_file}' berhasil dibuat/diperbarui.")
            # Tampilkan output standar jika ada
            if result.stdout:
                print(result.stdout)

        except FileNotFoundError:
            print("GAGAL: Perintah 'pylupdate6' tidak ditemukan.")
            print("Pastikan path ke PyQt6 (biasanya di dalam folder Scripts venv) ada di PATH environment variable Anda.")
            return
        except subprocess.CalledProcessError as e:
            print(f"GAGAL: Terjadi error saat menjalankan pylupdate6 untuk {lang}.")
            print(f"Error Output:\n{e.stderr}") # Tampilkan pesan error dari pylupdate6
            return
        # --------------------------------

    print("\nProses selesai. Semua file .ts telah diperbarui.")
    print("Langkah selanjutnya: Terjemahkan file .ts dengan Qt Linguist, lalu jalankan lrelease.")

if __name__ == '__main__':
    main()