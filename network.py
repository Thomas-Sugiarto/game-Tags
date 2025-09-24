# network.py
import socket
import pickle

class Network:
    def __init__(self, server_ip, server_port):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server = server_ip
        self.port = server_port
        self.addr = (self.server, self.port)
        self.player_id = self.connect()

    def get_player_id(self):
        return self.player_id

    def connect(self):
        try:
            self.client.connect(self.addr)
            return self.client.recv(2048).decode()
        except socket.error as e:
            print(f"Gagal terhubung ke server: {e}")
            return None

    def send(self, data):
        """
        PERBAIKAN: Mengirim data yang telah di-pickle ke server,
        selalu dengan header panjang data.
        """
        try:
            payload = pickle.dumps(data)
            # Membuat header 10-byte yang berisi panjang payload
            message = f"{len(payload):<10}".encode() + payload
            self.client.sendall(message)
        except socket.error as e:
            print(f"Gagal mengirim data: {e}")

    def receive(self):
        """Menerima data dari server dengan header panjang."""
        try:
            header_size = 10
            # 1. Terima header terlebih dahulu
            header_data = b''
            while len(header_data) < header_size:
                chunk = self.client.recv(header_size - len(header_data))
                if not chunk: return None
                header_data += chunk
            
            msglen = int(header_data.decode())

            # 2. Terima payload berdasarkan panjang dari header
            full_msg = b''
            while len(full_msg) < msglen:
                chunk = self.client.recv(min(msglen - len(full_msg), 4096))
                if not chunk: return None
                full_msg += chunk
            
            return pickle.loads(full_msg)

        except (EOFError, ConnectionResetError, pickle.UnpicklingError, OSError) as e:
            print(f"Koneksi terputus atau data korup: {e}")
            return None
        except ValueError:
            print("Menerima header yang tidak valid dari server.")
            return None

    def disconnect(self):
        self.client.close()