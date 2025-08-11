# FILE 4 # D:\7FX Automation\robots\HFT explosive m1\communication_client.py

import socket
import json
import time

class StatusClient:
    def __init__(self, port=65432):
        self.port = port
        self.host = '127.0.0.1'
        self.socket = None
        self.is_connected = False

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.is_connected = True
            return True
        except ConnectionRefusedError:
            self.is_connected = False
            return False
        except Exception as e:
            self.is_connected = False
            return False

    def send_status(self, account_number, status, extra_data=None):
        if not self.is_connected:
            if not self.connect():
                return

        message = {
            "account": account_number,
            "status": status,
            "timestamp": time.time()
        }

        try:
            json_string = json.dumps(message) + '\n'
            encoded_message = json_string.encode('utf-8')
            self.socket.sendall(encoded_message)
        except (BrokenPipeError, ConnectionResetError):
            self.is_connected = False
            self.connect()
            
    def close(self):
        if self.socket:
            self.socket.close()
        self.is_connected = False