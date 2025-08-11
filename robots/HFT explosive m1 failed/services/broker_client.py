# services/broker_client.py

import redis
import json
import threading
import time

class BrokerClient:
    """
    Klien untuk berkomunikasi dengan Message Broker (Redis).
    Menangani koneksi, publikasi pesan, dan berlangganan ke topik.
    """
    def __init__(self):
        self.is_connected = False
        self.listener_thread = None
        self.pubsub = None
        try:
            # Hubungkan ke server Redis lokal, decode_responses=False agar kita menerima bytes
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
            self.redis_client.ping() # Cek koneksi
            print("✅ Berhasil terhubung ke Message Broker (Redis).")
            self.is_connected = True
        except redis.exceptions.ConnectionError as e:
            print(f"❌ GAGAL terhubung ke Message Broker (Redis): {e}")
            print("-> Pastikan server Redis sudah berjalan di host='localhost' port=6379.")
            self.is_connected = False

    def publish(self, topic: str, message: dict):
        """
        Mempublikasikan sebuah pesan (dictionary) ke topik tertentu.
        Pesan akan diubah menjadi format JSON.
        """
        if not self.is_connected:
            return
        try:
            # Ubah dictionary ke string JSON sebelum dikirim
            json_message = json.dumps(message)
            self.redis_client.publish(topic, json_message)
        except Exception as e:
            print(f"Error saat mempublikasikan ke topik '{topic}': {e}")

    def subscribe(self, topic: str, callback_function):
        """
        Berlangganan ke sebuah topik dan menjalankan fungsi callback untuk setiap pesan.
        Proses mendengarkan akan berjalan di background thread.
        """
        if not self.is_connected:
            return

        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe(topic)
        
        # Buat dan jalankan thread untuk mendengarkan pesan
        self.listener_thread = threading.Thread(
            target=self._listener_loop,
            args=(callback_function,),
            daemon=True # Thread akan mati otomatis saat program utama keluar
        )
        self.listener_thread.start()
        print(f"🎧 Berlangganan ke topik: {topic}")

    def _listener_loop(self, callback_function):
        """Loop internal yang berjalan di thread untuk mendengarkan pesan."""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                try:
                    # Ubah pesan JSON (dalam format bytes) kembali ke dictionary
                    data = json.loads(message['data'].decode('utf-8'))
                    # Jalankan fungsi callback dengan data yang diterima
                    callback_function(data)
                except json.JSONDecodeError:
                    # Abaikan pesan yang bukan JSON valid
                    pass
                except Exception as e:
                    print(f"Error di dalam listener callback: {e}")

    def stop(self):
        """Menghentikan listener thread dengan rapi."""
        if self.pubsub:
            try:
                self.pubsub.unsubscribe()
                self.pubsub.close()
            except Exception as e:
                print(f"Error saat menutup koneksi pubsub: {e}")
        print("🔚 Koneksi ke Message Broker ditutup.")