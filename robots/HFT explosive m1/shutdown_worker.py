from PyQt6.QtCore import QObject, pyqtSignal

class ShutdownWorker(QObject):
    status_updated = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, bot_worker, worker_thread, heartbeat_worker, heartbeat_thread, status_client, account_number, full_shutdown=False):
        super().__init__()
        self.bot_worker = bot_worker
        self.worker_thread = worker_thread
        self.heartbeat_worker = heartbeat_worker
        self.heartbeat_thread = heartbeat_thread
        self.status_client = status_client
        self.account_number = account_number
        self.full_shutdown = full_shutdown

    def run(self):
        if self.bot_worker and self.worker_thread and self.worker_thread.isRunning():
            self.status_updated.emit(self.tr("Stopping bot engine..."))
            self.bot_worker.stop()
            self.worker_thread.quit()
            if not self.worker_thread.wait(5000):
                self.worker_thread.terminate()

        if self.full_shutdown:
            if self.heartbeat_worker and self.heartbeat_thread and self.heartbeat_thread.isRunning():
                self.status_updated.emit(self.tr("Stopping status reporter..."))
                self.heartbeat_worker.stop()
                self.heartbeat_thread.quit()
                self.heartbeat_thread.wait(3000)

            self.status_updated.emit(self.tr("Sending OFFLINE status to dashboard..."))
            self.status_client.send_status(self.account_number, "OFFLINE")
            self.status_client.close()

        self.status_updated.emit(self.tr("Shutdown process complete."))
        self.finished.emit()