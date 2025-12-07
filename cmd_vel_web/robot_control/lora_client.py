import serial  # PySerial kütüphanesi ile seri port (USB) üzerinden haberleşme

class LoRaClient:
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 115200):
        self.serial_connection = serial.Serial(port, baudrate, timeout=1, write_timeout=1)  # Seri portu açar

    def send_command(self, command: str) -> bool:
        try:
            # Serial bağlantısının açık olduğunu kontrol et
            if not self.serial_connection.is_open:
                print(f"[LoRa] HATA: Serial port kapalı!")
                return False
            
            # Komutu yalın metin olarak, satır sonu ile gönder
            msg_str = f"{command}\n"
            bytes_written = self.serial_connection.write(msg_str.encode('utf-8'))
            
            # Buffer'ı temizle - komutun gerçekten gönderilmesini garantile
            self.serial_connection.flush()
            
            print(f"[LoRa] TX: '{command}' ({bytes_written} byte gönderildi)")
            return True
        except Exception as e:
            print(f"[LoRa] HATA: Komut gönderilemedi - {e}")
            return False

try:
    lora_client = LoRaClient('/dev/ttyUSB0', 115200)
    print("[LoRa] Serial port bağlantısı başarıyla açıldı: /dev/ttyUSB0")
except (serial.SerialException, FileNotFoundError) as e:
    print(f"[LoRa] UYARI: Serial port açılamadı ({e}). Dummy modunda çalışılıyor.")
    class DummyLoRaClient:
        def send_command(self, command):
            print(f"[LoRa] DUMMY TX: '{command}' (gerçek gönderim yok - serial port bulunamadı)")
            return False
    lora_client = DummyLoRaClient() 
