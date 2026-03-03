import serial
import threading
import json

# Sıralı protokol: Raspberry mesaj gönderir → biz alırız (parse ederiz) → 1 sn sonra biz mesajımızı göndeririz (komut tam içeriği).
# İlk açılışta: arayüz karşıdan cevap gelene kadar saniyede bir mesaj göndermeyi dener. İlk cevap geldikten sonra karşıdan cevap gelene kadar bekler.
# İletişim reset: cevap gelmemiş olsa bile karşıya bir mesaj gönderir (Raspberry beklemeden çıksın).
# LoRa 240 byte: Raspberry kısa anahtar gönderir (t,s,i,b,g,r,x,y,c,n,o,p,m,e); burada uzun anahtarlara çeviriyoruz.
LORA_INTERVAL = 1.0

# Kısa -> uzun anahtar eşlemesi (Raspberry compact format)
_COMPACT_TO_LONG = {
    "t": "time", "s": "state", "i": "ssid", "b": "bssid", "g": "signal", "r": "rssi",
    "x": "rx", "y": "tx", "c": "channel", "n": "band", "o": "radio", "p": "cpu", "m": "ram", "e": "event",
}


def expand_compact_status(parsed):
    """LoRa'dan gelen kısa formatı (t, s, i, ...) uzun anahtarlara (time, state, ssid, ...) çevirir."""
    if not parsed or "time" in parsed:
        return parsed
    out = {}
    for short, long_key in _COMPACT_TO_LONG.items():
        if short not in parsed:
            continue
        v = parsed[short]
        if long_key == "state":
            out[long_key] = "connected" if v == "c" else "disconnected"
        elif long_key == "signal":
            out[long_key] = f"{v}%" if isinstance(v, (int, float)) else str(v)
        elif long_key == "rssi":
            out[long_key] = f"{int(v)} dBm" if isinstance(v, (int, float)) else str(v)
        elif long_key in ("rx", "tx"):
            out[long_key] = f"{int(v)} Mbps" if isinstance(v, (int, float)) else str(v)
        elif long_key == "band":
            out[long_key] = "5 GHz" if v == "5G" else ("2.4 GHz" if v == "2.4" else str(v))
        elif long_key in ("cpu", "ram"):
            out[long_key] = f"{v}%" if isinstance(v, (int, float)) else str(v)
        else:
            out[long_key] = v
    return out

class LoRaClient:
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 9600):
        self.serial_connection = serial.Serial(port, baudrate, timeout=1, write_timeout=1)
        self.last_message = "-"
        self.last_parsed_status = None  # LoRa'dan gelen son JSON (dict); Wi-Fi durumu
        self._lock = threading.Lock()
        self._running = True
        self._outgoing_message = "OK"
        self._outgoing_lock = threading.Lock()
        # İlk açılış: karşıdan hiç cevap gelmediyse saniyede bir gönder; ilk cevap geldikten sonra karşıdan cevap gelene kadar bekle
        self._first_response_received = False
        self._response_received_since_send = False
        self._state_lock = threading.Lock()
        # Arka planda mesaj okuma thread'ini başlat
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        # Her 1 saniyede bir giden mesajı gönderen thread
        self._send_interval_thread = threading.Thread(target=self._send_interval_loop, daemon=True)
        self._send_interval_thread.start()
    
    def _send_interval_loop(self):
        """Her 1 saniyede bir: ilk cevap gelene kadar sürekli dene; ilk cevaptan sonra karşıdan cevap gelene kadar bekleyip sonra gönder."""
        while self._running:
            threading.Event().wait(LORA_INTERVAL)
            if not self._running:
                break
            with self._state_lock:
                first_ok = self._first_response_received
                response_ok = self._response_received_since_send
            # İlk cevap gelene kadar: her saniye gönder. İlk cevap geldikten sonra: sadece karşıdan cevap geldiyse gönder
            if not first_ok or response_ok:
                with self._outgoing_lock:
                    msg = self._outgoing_message
                if msg and self.serial_connection.is_open:
                    try:
                        self.serial_connection.write((msg + "\n").encode("utf-8"))
                        self.serial_connection.flush()
                        with self._state_lock:
                            self._response_received_since_send = False
                        print(f"[LoRa] TX (1sn): '{msg}'")
                    except Exception as e:
                        print(f"[LoRa] HATA: Aralıklı gönderim - {e}")

    def reset_communication(self) -> bool:
        """İletişim reset: cevap gelmemiş olsa bile karşıya hemen bir mesaj gönderir (Raspberry beklemeden çıksın)."""
        if not self.serial_connection.is_open:
            print("[LoRa] İletişim reset: port kapalı")
            return False
        try:
            msg = "OK"
            self.serial_connection.write((msg + "\n").encode("utf-8"))
            self.serial_connection.flush()
            with self._state_lock:
                self._response_received_since_send = False  # bir sonraki periyodik gönderim yine cevap beklesin
            print("[LoRa] İletişim reset: mesaj gönderildi")
            return True
        except Exception as e:
            print(f"[LoRa] İletişim reset hatası: {e}")
            return False

    def set_outgoing_message(self, message: str):
        """Her 1 saniyede gönderilecek mesajı ayarla (komut tam içeriği; örn. 'ss', 'ww'). Boş bırakılırsa 'OK' kullanılır."""
        with self._outgoing_lock:
            self._outgoing_message = message if message else "OK"

    def _read_loop(self):
        """Arka planda sürekli mesaj okuma döngüsü"""
        while self._running:
            try:
                self.read_message()
            except Exception as e:
                print(f"[LoRa] HATA: Okuma döngüsünde hata - {e}")
            threading.Event().wait(1.0)  # 1 saniye bekle

    def send_command(self, command: str) -> bool:
        if not command:
            return False
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
                    message = line.decode('utf-8', errors='ignore').strip()
                    with self._lock:
                        self.last_message = message
                    with self._state_lock:
                        self._first_response_received = True
                        self._response_received_since_send = True
                    # JSON ise parse et
                    if message.startswith('{'):
                        try:
                            parsed = json.loads(message)
                            with self._lock:
                                self.last_parsed_status = expand_compact_status(parsed)
                            print(f"[LoRa] RX (JSON): state={parsed.get('state', parsed.get('s','?'))} ssid={parsed.get('ssid', parsed.get('i','?'))} ...")
                        except json.JSONDecodeError as e:
                            print(f"[LoRa] RX (ham): '{message[:60]}...' (JSON parse hatası: {e})")
                    else:
                        print(f"[LoRa] RX: '{message}'")
                    return message
        except Exception as e:
            print(f"[LoRa] HATA: Mesaj okunamadı - {e}")
        return None

    def get_last_message(self) -> str:
        """Son alınan ham mesajı döndürür"""
        with self._lock:
            return self.last_message

    def get_parsed_status(self) -> dict:
        """LoRa'dan gelen son Wi-Fi durumunu (JSON parse edilmiş dict) döndürür. Yoksa None."""
        with self._lock:
            return self.last_parsed_status.copy() if self.last_parsed_status else None

try:
    lora_client = LoRaClient('/dev/ttyUSB0', 9600)
    print("[LoRa] Serial port bağlantısı başarıyla açıldı: /dev/ttyUSB0 (9600 baud)")
except (serial.SerialException, FileNotFoundError) as e:
    print(f"[LoRa] UYARI: Serial port açılamadı ({e}). Dummy modunda çalışılıyor.")
    class DummyLoRaClient:
        def __init__(self):
            self.last_message = "-"
            self.last_parsed_status = None
        
        def set_outgoing_message(self, message: str):
            pass

        def reset_communication(self) -> bool:
            print("[LoRa] DUMMY: İletişim reset (gerçek gönderim yok)")
            return False
        
        def send_command(self, command):
            print(f"[LoRa] DUMMY TX: '{command}' (gerçek gönderim yok - serial port bulunamadı)")
            return False
        
        def read_message(self):
            return None
        
        def get_last_message(self):
            return self.last_message
        
        def get_parsed_status(self):
            return self.last_parsed_status
    
    lora_client = DummyLoRaClient() 
