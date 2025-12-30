import serial  # PySerial kütüphanesi ile seri port (USB) üzerinden haberleşme
import threading

class LoRaClient:
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 9600):
        self.serial_connection = serial.Serial(port, baudrate, timeout=1, write_timeout=1)  # Seri portu açar
        self.last_message = "-"  # Son alınan mesajı sakla
        self._lock = threading.Lock()  # Thread-safe erişim için
        self._running = True
        # Arka planda mesaj okuma thread'ini başlat
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
    
    def _read_loop(self):
        """Arka planda sürekli mesaj okuma döngüsü"""
        while self._running:
            try:
                self.read_message()
            except Exception as e:
                print(f"[LoRa] HATA: Okuma döngüsünde hata - {e}")
            threading.Event().wait(1.0)  # 1 saniye bekle

    def send_command(self, command: str) -> bool:
        try:
            if not self.serial_connection.is_open:
                print(f"[LoRa] HATA: Serial port kapalı!")
                return False
            
            msg_str = f"{command}\n"
            bytes_written = self.serial_connection.write(msg_str.encode('utf-8'))
            
            # Buffer'ı temizle - komutun gerçekten gönderilmesini garantile
            self.serial_connection.flush()
            
            print(f"[LoRa] TX: '{command}' ({bytes_written} byte gönderildi)")
            return True
        except Exception as e:
            print(f"[LoRa] HATA: Komut gönderilemedi - {e}")
            return False

    def read_message(self) -> str:
        """Seri porttan mesaj okur ve son mesajı günceller"""
        try:
            if not self.serial_connection.is_open:
                return None
            
            # Seri porttan veri oku
            if self.serial_connection.in_waiting > 0:
                line = self.serial_connection.readline()
                if line:
                    # Ham veri olarak sakla - sadece decode yap, strip yapma
                    message = line.decode('utf-8', errors='ignore')
                    with self._lock:
                        self.last_message = message
                    print(f"[LoRa] RX: '{message.rstrip()}'")
                    return message
        except Exception as e:
            print(f"[LoRa] HATA: Mesaj okunamadı - {e}")
        return None

    def get_last_message(self) -> str:
        """Son alınan mesajı döndürür"""
        with self._lock:
            return self.last_message

try:
    lora_client = LoRaClient('/dev/ttyUSB0', 9600)
    print("[LoRa] Serial port bağlantısı başarıyla açıldı: /dev/ttyUSB0 (9600 baud)")
except (serial.SerialException, FileNotFoundError) as e:
    print(f"[LoRa] UYARI: Serial port açılamadı ({e}). Dummy modunda çalışılıyor.")
    class DummyLoRaClient:
        def __init__(self):
            self.last_message = "-"
        
        def send_command(self, command):
            print(f"[LoRa] DUMMY TX: '{command}' (gerçek gönderim yok - serial port bulunamadı)")
            return False
        
        def read_message(self):
            return None
        
        def get_last_message(self):
            return self.last_message
    
    lora_client = DummyLoRaClient() 
