from collections import deque
import numpy as np

class SpreadAnalyzer:
    def __init__(self, observation_period=200, tolerance_multiplier=1.25):
        """
        Menganalisis spread secara real-time.
        :param observation_period: Jumlah tick terakhir yang digunakan untuk menghitung rata-rata.
        :param tolerance_multiplier: Pengali untuk ambang batas. Spread dianggap tipis jika
                                     di bawah (rata-rata * multiplier). 1.25 berarti 25% di atas rata-rata.
        """
        self.history = deque(maxlen=observation_period)
        self.tolerance_multiplier = tolerance_multiplier
        self.average_spread = 0

    def add_spread(self, spread: int):
        """Menambahkan data spread baru dan menghitung ulang rata-rata."""
        self.history.append(spread)
        if self.history:
            self.average_spread = np.mean(self.history)

    def is_spread_tight(self, current_spread: int) -> bool:
        """Mengecek apakah spread saat ini dianggap 'tipis'."""
        if not self.is_ready():
            return False # Belum cukup data untuk membuat keputusan

        # Spread dianggap tipis jika di bawah rata-rata dikali toleransi
        return current_spread <= (self.average_spread * self.tolerance_multiplier)

    def is_ready(self) -> bool:
        """Mengecek apakah data sudah cukup untuk analisis (misal: 50% dari periode observasi)."""
        return len(self.history) > (self.history.maxlen / 2)