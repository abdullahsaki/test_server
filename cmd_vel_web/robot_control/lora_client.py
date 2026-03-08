import serial
import threading
import json

# Sıralı protokol (süre yok, sadece mesaj bekleme):
# - Arayüz: Mesaj bekler → mesaj gelince komut varsa komutu, yoksa impuls (OK) gönderir → tekrar mesaj bekler.
# - Raspberry: Mesaj gönderir → karşıdan mesaj bekler → mesaj gelince işler ve yeni mesaj gönderir.
# LoRa 240 byte: Raspberry kısa anahtar gönderir (t,s,i,b,g,r,x,y,c,n,o,p,m,e,w,u); burada uzun anahtarlara çeviriyoruz.

# Kısa -> uzun anahtar eşlemesi (Raspberry compact format)
_COMPACT_TO_LONG = {
    "t": "time", "s": "state", "i": "ssid", "b": "bssid", "g": "signal", "r": "rssi",
    "x": "rx", "y": "tx", "c": "channel", "n": "band", "o": "radio", "p": "cpu", "m": "ram", "e": "event",
    "w": "win_batt", "u": "rpi_batt",
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
        elif long_key in ("win_batt", "rpi_batt"):
            out[long_key] = f"{v}%" if isinstance(v, (int, float)) else str(v)
        else:
            out[long_key] = v
    return out


def _process_received_line(client, message: str) -> None:
    """Alınan mesaj satırını işle (last_message, last_parsed_status, log)."""
    with client._lock:
        client.last_message = message
    if message.startswith("{"):
        try:
            parsed = json.loads(message)
            with client._lock:
                client.last_parsed_status = expand_compact_status(parsed)
            print(f"[LoRa] RX (JSON): state={parsed.get('state', parsed.get('s','?'))} ssid={parsed.get('ssid', parsed.get('i','?'))} ...")
        except json.JSONDecodeError as e:
            print(f"[LoRa] RX (ham): '{message[:60]}...' (JSON parse hatası: {e})")
    else:
        print(f"[LoRa] RX: '{message}'")


class LoRaClient:
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 9600):
        # Bloklayan okuma için timeout=None (mesaj gelene kadar bekler)
        self.serial_connection = serial.Serial(port, baudrate, timeout=None, write_timeout=1)
        self.last_message = "-"
        self.last_parsed_status = None
        self._lock = threading.Lock()
        self._running = True
        self._outgoing_message = "OK"
        self._outgoing_lock = threading.Lock()
        # Tek thread: mesaj bekle → alınca cevap gönder (komut veya OK)
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def _read_loop(self):
        """Mesaj bekler (bloklayan okuma); mesaj gelince komut varsa komutu yoksa OK gönderir, sonra tekrar bekler."""
        while self._running and self.serial_connection.is_open:
            try:
                line = self.serial_connection.readline()
                if not line:
                    continue
                message = line.decode("utf-8", errors="ignore").strip()
                if not message:
                    continue
                _process_received_line(self, message)
                # Cevap gönder: bekleyen komut varsa onu, yoksa OK
                with self._outgoing_lock:
                    msg = self._outgoing_message or "OK"
                    self._outgoing_message = "OK"
                try:
                    self.serial_connection.write((msg + "\n").encode("utf-8"))
                    self.serial_connection.flush()
                    print(f"[LoRa] TX: '{msg}'")
                except Exception as e:
                    print(f"[LoRa] HATA: Cevap gönderilemedi - {e}")
            except Exception as e:
                if self._running:
                    print(f"[LoRa] HATA: Okuma/cevap döngüsü - {e}")
                break

    def reset_communication(self) -> bool:
        """İletişim reset: Raspberry beklemeden çıksın diye hemen OK gönderir."""
        if not self.serial_connection.is_open:
            print("[LoRa] İletişim reset: port kapalı")
            return False
        try:
            self.serial_connection.write(("OK\n").encode("utf-8"))
            self.serial_connection.flush()
            print("[LoRa] İletişim reset: OK gönderildi")
            return True
        except Exception as e:
            print(f"[LoRa] İletişim reset hatası: {e}")
            return False

    def set_outgoing_message(self, message: str):
        """Bir sonraki cevapta gönderilecek mesajı ayarla (komut veya boş/OK)."""
        with self._outgoing_lock:
            self._outgoing_message = message if message else "OK"

    def send_command(self, command: str) -> bool:
        """Komutu 'bekleyen cevap' olarak ayarlar; bir sonraki Raspberry mesajında bu komut gönderilir."""
        if not command:
            return False
        if not self.serial_connection.is_open:
            print("[LoRa] HATA: Serial port kapalı!")
            return False
        self.set_outgoing_message(command)
        print(f"[LoRa] Komut kuyruğa alındı (sonraki cevapta gönderilecek): '{command}'")
        return True

    def read_message(self) -> str:
        """Non-blocking: seri portta veri varsa oku ve güncelle. Yoksa None."""
        try:
            if not self.serial_connection.is_open or self.serial_connection.in_waiting == 0:
                return None
            line = self.serial_connection.readline()
            if not line:
                return None
            message = line.decode("utf-8", errors="ignore").strip()
            _process_received_line(self, message)
            return message
        except Exception as e:
            print(f"[LoRa] HATA: Mesaj okunamadı - {e}")
        return None

    def get_last_message(self) -> str:
        with self._lock:
            return self.last_message

    def get_parsed_status(self) -> dict:
        with self._lock:
            return self.last_parsed_status.copy() if self.last_parsed_status else None


try:
    lora_client = LoRaClient("/dev/ttyUSB0", 9600)
    print("[LoRa] Serial port açıldı: /dev/ttyUSB0 (9600 baud), mesaj-bekleme modu")
except (serial.SerialException, FileNotFoundError) as e:
    print(f"[LoRa] UYARI: Serial port açılamadı ({e}). Dummy modunda çalışılıyor.")
    class DummyLoRaClient:
        def __init__(self):
            self.last_message = "-"
            self.last_parsed_status = None
        def set_outgoing_message(self, message: str):
            pass
        def reset_communication(self) -> bool:
            print("[LoRa] DUMMY: İletişim reset")
            return False
        def send_command(self, command):
            print(f"[LoRa] DUMMY: Komut kuyruğa alındı '{command}'")
            return bool(command)
        def read_message(self):
            return None
        def get_last_message(self):
            return self.last_message
        def get_parsed_status(self):
            return self.last_parsed_status
    lora_client = DummyLoRaClient()
