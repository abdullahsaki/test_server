#!/usr/bin/env python3
"""
Raspberry Pi Birleşik LoRa Bridge

1. Windows PC'den TCP ile veri al → JSON'a çevir → LoRa ile Ubuntu'ya gönder
   (Buffer boşsa boş JSON {} gönderilir; Windows bağlı değilken yine de el sıkışma devam eder.)
2. LoRa'dan Ubuntu cevabını bekle → mesaj gelince işle (komut/OK) → yeni mesaj gönderme sırası gelir
3. /battery_state'ten batarya yüzdesi al → Windows verisiyle birleştirip LoRa'ya ekler
4. /state topic'ine event kodu (0,1,2,-1) saniyede bir publish edilir

Sıralı protokol: RPi gönderir → Ubuntu cevap verene kadar bekler → cevap gelince işler → tekrar gönderir.
"""
import socket
import serial
import time
import subprocess
import threading
import json
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Int32

# Konfigürasyon
TCP_PORT = 5001
LORA_PORT = "/dev/ttyAMA0"
LORA_BAUDRATE = 9600
LORA_MAX_BYTES = 240  # LoRa paket boyut sınırı (byte)

def _to_num(s, default=0):
    try:
        return float(str(s).replace("%", "").replace(" dBm", "").replace(" Mbps", "").strip())
    except (ValueError, TypeError):
        return default


def parse_windows_status_line(line):
    out = {}
    for part in line.split("|"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def compact_status_for_lora(obj):
    out = {}
    if "time" in obj:
        raw = obj["time"]
        parts = raw.split()
        for p in parts:
            if len(p) == 8 and ":" in p and p.count(":") == 2:
                out["t"] = p
                break
        if "t" not in out:
            out["t"] = raw[-8:] if len(raw) >= 8 else raw
    if "state" in obj:
        s = obj["state"].strip().lower()
        out["s"] = "c" if s == "connected" else "d"
    if "ssid" in obj:
        out["i"] = (obj["ssid"].strip() or "")[:24]
    if "bssid" in obj:
        out["b"] = (obj["bssid"] or "").strip()
    if "signal" in obj:
        out["g"] = _to_num(obj["signal"], 0)
    if "rssi" in obj:
        out["r"] = _to_num(obj["rssi"], 0)
    if "rx" in obj:
        out["x"] = _to_num(obj["rx"], 0)
    if "tx" in obj:
        out["y"] = _to_num(obj["tx"], 0)
    if "channel" in obj:
        out["c"] = _to_num(obj["channel"], 0)
    if "band" in obj:
        b = (obj["band"] or "").replace(" GHz", "").replace("*", "").strip()
        out["n"] = "5G" if b == "5" else ("2.4" if b == "2.4" else b[:4])
    if "radio" in obj:
        r = (obj["radio"] or "").lower()
        if "ax" in r:
            out["o"] = "ax"
        elif "ac" in r:
            out["o"] = "ac"
        elif "n" in r:
            out["o"] = "n"
        else:
            out["o"] = r[-2:] if len(r) >= 2 else r
    if "cpu" in obj:
        out["p"] = _to_num(obj["cpu"], 0)
    if "ram" in obj:
        out["m"] = _to_num(obj["ram"], 0)
    if "event" in obj:
        out["e"] = obj["event"].strip()
    # Windows ve Raspberry batarya yüzdeleri (wbatt, rbatt)
    if "wbatt" in obj:
        out["w"] = _to_num(obj["wbatt"], 0)
    if "rbatt" in obj:
        out["u"] = _to_num(obj["rbatt"], 0)
    return out


# Robot kontrol parametreleri
LIN_VEL_STEP_SIZE = 0.05
ANG_VEL_STEP_SIZE = 0.1
MAX_LIN_VEL = 0.30
MAX_ANG_VEL = 1.82

def constrain(val, min_val, max_val):
    return max(min_val, min(max_val, val))

class RaspberryLoRaBridgeNode(Node):
    def __init__(self):
        super().__init__('raspberry_lora_bridge_node')
        self.get_logger().info("Raspberry Pi Birleşik LoRa Bridge Başlatıldı")
        
        # LoRa seri portunu aç
        try:
            self.lora_serial = serial.Serial(
                LORA_PORT,
                LORA_BAUDRATE,
                timeout=None,  # Bloklayan okuma: karşıdan mesaj gelene kadar bekle
                write_timeout=1.0
            )
            self.lora_serial.reset_input_buffer()  # Buffer'ı temizle
            self.lora_serial.reset_output_buffer()
            self.get_logger().info(f"LoRa seri portu açıldı: {LORA_PORT} ({LORA_BAUDRATE} baud)")
        except serial.SerialException as e:
            self.get_logger().error(f"LoRa seri portu açılamadı: {e}")
            self.get_logger().error(f"   Port yolunu kontrol edin: {LORA_PORT}")
            self.get_logger().error(f"   Kullanıcının 'dialout' grubunda olduğundan emin olun: sudo usermod -a -G dialout $USER")
            raise e
        
        # TCP sunucusunu başlat
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('0.0.0.0', TCP_PORT))
            self.tcp_socket.listen(1)
            self.tcp_socket.settimeout(1.0)
            self.get_logger().info(f" TCP sunucu başlatıldı: 0.0.0.0:{TCP_PORT}")
        except Exception as e:
            self.get_logger().error(f" TCP sunucu başlatılamadı: {e}")
            raise e
        
        # =======================================================
        # ROS2 Publisher / Subscriber
        # =======================================================
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.state_pub = self.create_publisher(Int32, '/state', 10)
        self.target_lin = 0.0
        self.target_ang = 0.0
        self.last_event_code = 0  # 0=yok, 1=BandSteering, 2=Roaming, -1=hata
        self.twist_msg = Twist()
        # /battery_state topiğinden gelen batarya yüzdesi (0–100 arası float)
        self.rpi_batt_percent = None
        self.batt_sub = self.create_subscription(
            BatteryState,
            '/battery_state',
            self.battery_callback,
            10,
        )
        
        # =======================================================
        # Launch Process Yönetimi
        # =======================================================
        self.robot_launch_process = None
        self.test_launch_process = None
        self.mapping_launch_process = None
        self.map_save_launch_process = None
        
        # =======================================================
        # Veri Buffer (Ethernet'ten gelen veriler için)
        # =======================================================
        self.data_buffer = []
        self.buffer_lock = threading.Lock()
        # Sıralı LoRa: karşıdan mesaj gelene kadar yeni mesaj göndermiyoruz
        self.lora_waiting_reply = False
        self.lora_running = True
        self.lora_thread = threading.Thread(target=self._lora_cycle_loop, daemon=True)
        self.lora_thread.start()

        self.state_timer = self.create_timer(1.0, self._state_timer_callback)
        self.client_socket = None
        self.client_file = None
        self.tcp_running = True
        threading.Thread(target=self.tcp_read_loop, daemon=True).start()
        
        self.get_logger().info("Tüm özellikler başlatıldı. Sistem hazır.")

    def _state_timer_callback(self):
        msg = Int32()
        msg.data = self.last_event_code
        self.state_pub.publish(msg)

    def battery_callback(self, msg: BatteryState):
        try:
            perc = msg.percentage
            if perc is None or perc < 0:
                return
            if 0.0 <= perc <= 1.0:
                perc = perc * 100.0
            self.rpi_batt_percent = perc
        except Exception:
            pass

    def _close(self, obj):
        if obj:
            try:
                obj.close()
            except Exception:
                pass

    def _stop_process(self, proc):
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    def cleanup(self):
        self.lora_running = False
        self.tcp_running = False
        self._close(self.client_file)
        self._close(self.client_socket)
        self._close(self.tcp_socket)
        if self.lora_serial and self.lora_serial.is_open:
            self._close(self.lora_serial)
        self._stop_process(self.robot_launch_process)
        self._stop_process(self.test_launch_process)
        self._stop_process(self.mapping_launch_process)
        self._stop_process(self.map_save_launch_process)
    
    def send_to_lora(self, data):
        """Veriyi LoRa üzerinden gönder (ham string; genelde JSON string)."""
        try:
            data_bytes = (data + '\n').encode('utf-8')
            self.lora_serial.write(data_bytes)
            self.lora_serial.flush()
            self.get_logger().info(f'[LoRa TX] {data[:80]}...')
            return True
        except serial.SerialException as e:
            self.get_logger().error(f"LoRa gönderme hatası: {e}")
            return False
    
    def tcp_read_loop(self):
        """TCP okuma döngüsü (ayrı thread'de çalışır)"""
        while self.tcp_running and rclpy.ok():
            try:
                if self.client_socket is None:
                    # Yeni bağlantı bekle
                    try:
                        self.client_socket, client_addr = self.tcp_socket.accept()
                        self.get_logger().info(f"TCP bağlantı kabul edildi: {client_addr}")
                        self.client_file = self.client_socket.makefile('r', encoding='utf-8')
                    except socket.timeout:
                        time.sleep(0.1)
                        continue
                    except Exception as e:
                        self.get_logger().error(f"TCP bağlantı hatası: {e}")
                        time.sleep(1)
                        continue
                
                # Bağlı istemciden veri oku
                try:
                    line = self.client_file.readline()
                    if line:
                        line = line.strip()
                        if line:
                            with self.buffer_lock:
                                self.data_buffer.append(line)
                    elif not line:
                        # Bağlantı kapandı
                        raise ConnectionError("Bağlantı kapandı")
                except (ConnectionError, OSError):
                    self._close(self.client_file)
                    self._close(self.client_socket)
                    self.client_socket = None
                    self.client_file = None
                    time.sleep(0.5)
                except Exception as e:
                    self.get_logger().error(f"TCP okuma hatası: {e}")
                    time.sleep(0.1)
            except Exception as e:
                self.get_logger().error(f"TCP döngü hatası: {e}")
                time.sleep(1)
    
    def _lora_cycle_loop(self):
        """Süre yok: gönder → karşıdan mesaj bekle → mesaj gelince işle → tekrar gönder (döngüler arasında 1 sn bekleme)."""
        while self.lora_running and rclpy.ok():
            try:
                if self.lora_waiting_reply:
                    line = self.lora_serial.readline()
                    if not line:
                        continue
                    msg = line.decode("utf-8", errors="ignore").strip()
                    if msg:
                        self.process_lora_message(msg)
                    self.lora_waiting_reply = False
                else:
                    if self.send_from_buffer():
                        self.lora_waiting_reply = True
                    else:
                        self.lora_waiting_reply = self.send_to_lora("{}")
                time.sleep(1.0)
            except Exception as e:
                if self.lora_running:
                    self.get_logger().warn(f"LoRa döngü hatası: {e}")
                break

    def process_lora_message(self, msg: str):
        """LoRa'dan gelen mesajı işle (komut veya impuls); sıradaki gönderime izin verir."""
        try:
            self.get_logger().info(f"LoRa RX: {msg[:120]}...")
            if msg == "ww":
                self.target_lin = constrain(self.target_lin + LIN_VEL_STEP_SIZE, -MAX_LIN_VEL, MAX_LIN_VEL)
            elif msg == "xx":
                self.target_lin = constrain(self.target_lin - LIN_VEL_STEP_SIZE, -MAX_LIN_VEL, MAX_LIN_VEL)
            elif msg == "aa":
                self.target_ang = constrain(self.target_ang + ANG_VEL_STEP_SIZE, -MAX_ANG_VEL, MAX_ANG_VEL)
            elif msg == "dd":
                self.target_ang = constrain(self.target_ang - ANG_VEL_STEP_SIZE, -MAX_ANG_VEL, MAX_ANG_VEL)
            elif msg == "ss":
                self.target_lin = 0.0
                self.target_ang = 0.0

            if msg in ("ww", "xx", "aa", "dd", "ss"):
                self.twist_msg.linear.x = self.target_lin
                self.twist_msg.angular.z = self.target_ang
                self.cmd_vel_pub.publish(self.twist_msg)

            if msg == "robot_launch":
                self.start_robot_launch(["ros2", "launch", "turtlebot3_bringup", "robot.launch.py"])
            elif msg == "robot_bitir":
                self.stop_robot_launch()
            elif msg == "rota_testi":
                self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "rota_test.launch.py"])
            elif msg == "roaming_testi":
                self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "roaming_test.launch.py"])
            elif msg == "steering_testi":
                self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "steering_test.launch.py"])
            elif msg == "ortak_testi":
                self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "ortak_test.launch.py"])
            elif msg == "mapping_baslat":
                self.start_mapping_launch(["ros2", "launch", "turtlebot3_tests", "mapping.launch.py"])
            elif msg == "mapping_bitir":
                self.finish_mapping_with_save()
            elif msg == "testi_bitir":
                self.stop_test_launch()
        except Exception as e:
            self.get_logger().warn(f"LoRa mesaj işleme hatası: {e}")

    def send_from_buffer(self):
        if self.lora_waiting_reply:
            return False
        with self.buffer_lock:
            if not self.data_buffer:
                return False
            data_line = self.data_buffer[-1]
            self.data_buffer = [data_line]  # Son veriyi tut; yeni TCP verisi gelene kadar tekrar gönder
        try:
            obj = parse_windows_status_line(data_line)
            event_code = 0
            if "ERROR" in data_line:
                event_code = -1
            elif "event" in obj:
                try:
                    event_code = int(obj["event"].strip())
                    if event_code not in (1, 2):
                        event_code = 0
                except (ValueError, TypeError):
                    pass
            self.last_event_code = event_code
            if self.rpi_batt_percent is not None:
                obj["rbatt"] = f"{self.rpi_batt_percent:.0f}%"
            compact = compact_status_for_lora(obj)
            json_str = json.dumps(compact, ensure_ascii=False)
            max_payload = LORA_MAX_BYTES - 1
            while len(json_str.encode("utf-8")) > max_payload and "i" in compact:
                compact["i"] = compact["i"][:-1] if len(compact["i"]) > 1 else ""
                json_str = json.dumps(compact, ensure_ascii=False)
                if not compact["i"]:
                    break
        except Exception as e:
            self.get_logger().warn(f"JSON dönüşüm hatası, ham gönderim: {e}")
            max_payload = LORA_MAX_BYTES - 1
            b = data_line.encode("utf-8")
            json_str = b[:max_payload].decode("utf-8", errors="ignore") if len(b) > max_payload else data_line
        return self.send_to_lora(json_str)
    
    def start_robot_launch(self, cmd):
        """Robot launch dosyasını başlat"""
        if self.robot_launch_process is not None:
            if self.robot_launch_process.poll() is None:
                self.get_logger().info("Robot launch zaten çalışıyor. Dokunulmadı.")
                return
        
        self.get_logger().info("Robot launch başlatılıyor...")
        self.robot_launch_process = subprocess.Popen(cmd)

    def stop_robot_launch(self):
        self._stop_process(self.robot_launch_process)
        self.robot_launch_process = None
    
    def start_test_launch(self, cmd):
        self._stop_process(self.test_launch_process)
        self.test_launch_process = subprocess.Popen(cmd)

    def start_mapping_launch(self, cmd):
        """Mapping launch dosyasını başlat."""
        if self.mapping_launch_process is not None and self.mapping_launch_process.poll() is None:
            self.get_logger().info("Mapping launch zaten çalışıyor. Dokunulmadı.")
            return
        self.get_logger().info("Mapping launch başlatılıyor...")
        self.mapping_launch_process = subprocess.Popen(cmd)

    def start_map_save_launch(self, cmd):
        """Map save launch dosyasını başlat."""
        if self.map_save_launch_process is not None and self.map_save_launch_process.poll() is None:
            self.get_logger().info("Map save launch zaten çalışıyor. Dokunulmadı.")
            return
        self.get_logger().info("Map save launch başlatılıyor...")
        self.map_save_launch_process = subprocess.Popen(cmd)

    def stop_mapping_and_save(self):
        self._stop_process(self.mapping_launch_process)
        self._stop_process(self.map_save_launch_process)
        self.mapping_launch_process = None
        self.map_save_launch_process = None

    def finish_mapping_with_save(self):
        """
        Mapping bitirme akışı:
        1) Mapping çalışıyorsa map_save.launch'ı başlat.
        2) 15 saniye bekle.
        3) Mapping ve map_save launch'larını durdur.
        """
        if self.mapping_launch_process is None or self.mapping_launch_process.poll() is not None:
            self.get_logger().warn("Mapping launch çalışmıyor, 'mapping_bitir' komutu yok sayıldı.")
            return

        # 1) map_save.launch'ı başlat
        self.start_map_save_launch(["ros2", "launch", "turtlebot3_tests", "map_save.launch.py"])

        # 2) 15 saniye sonra her ikisini de durdurmak için arka plan thread'i
        def _worker():
            self.get_logger().info("Map save için 15 saniye bekleniyor...")
            time.sleep(15)
            self.get_logger().info("15 saniye doldu, mapping ve map_save sonlandırılıyor...")
            self.stop_mapping_and_save()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
    
    def stop_test_launch(self):
        self._stop_process(self.test_launch_process)
        self.test_launch_process = None
    
    
    def on_shutdown(self):
        """Düğüm kapanırken robotu durdur ve kaynakları temizle"""
        self.get_logger().info("Kapatılıyor... Robot durduruluyor ve kaynaklar temizleniyor.")
        # Robotu durdur
        stop_twist = Twist()
        stop_twist.linear.x = 0.0
        stop_twist.angular.z = 0.0
        self.cmd_vel_pub.publish(stop_twist)
        # Kaynakları temizle
        self.cleanup()

def main(args=None):
    rclpy.init(args=args)
    
    node = None
    try:
        node = RaspberryLoRaBridgeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nDurduruldu (Ctrl+C)")
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        if node is not None:
            node.on_shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
