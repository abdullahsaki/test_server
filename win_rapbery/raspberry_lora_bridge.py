#!/usr/bin/env python3
"""
Raspberry Pi Birleşik LoRa Bridge
1. Windows PC'den Ethernet (TCP) üzerinden veri al → JSON stringe çevir → LoRa ile Ubuntu'ya sıralı gönder
2. LoRa'dan Ubuntu'dan gelen mesajı bekle (komut tam içeriği); mesaj gelmeden yeni mesaj gönderme
Sıralı iletişim: RPi mesaj gönderir → Ubuntu mesajı alır → 1 sn sonra Ubuntu kendi mesajını gönderir →
RPi o mesajı alır → RPi yeni mesaj gönderir. Her iki tarafta 1 saniyede bir işlem.
"""
import socket
import serial
import time
import sys
import subprocess
import threading
import json
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

# Konfigürasyon
TCP_PORT = 5001
LORA_PORT = "/dev/ttyAMA0"
LORA_BAUDRATE = 9600
LORA_INTERVAL = 1.0  # Her iki cihazda da 1 saniyede bir işlem
LORA_MAX_BYTES = 240  # LoRa paket boyut sınırı (byte)

def parse_windows_status_line(line):
    """Windows WifiStatusTcpSender satırını parse edip dict döndürür. JSON ile LoRa'ya gönderilir."""
    out = {}
    for part in line.split("|"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def compact_status_for_lora(obj):
    """
    Parse edilmiş Windows durumunu LoRa 240 byte sınırına uygun kısa formata çevirir.
    Kısa anahtarlar: t=time, s=state, i=ssid, b=bssid, g=signal, r=rssi, x=rx, y=tx,
    c=channel, n=band, o=radio, p=cpu, m=ram, e=event
    """
    def num(s, default=0):
        try:
            return float(str(s).replace("%", "").replace(" dBm", "").replace(" Mbps", "").strip())
        except (ValueError, TypeError):
            return default

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
        out["g"] = num(obj["signal"], 0)
    if "rssi" in obj:
        out["r"] = num(obj["rssi"], 0)
    if "rx" in obj:
        out["x"] = num(obj["rx"], 0)
    if "tx" in obj:
        out["y"] = num(obj["tx"], 0)
    if "channel" in obj:
        out["c"] = num(obj["channel"], 0)
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
        out["p"] = num(obj["cpu"], 0)
    if "ram" in obj:
        out["m"] = num(obj["ram"], 0)
    if "event" in obj:
        out["e"] = obj["event"].strip()
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
        self.get_logger().info("📡 Raspberry Pi Birleşik LoRa Bridge Başlatıldı 🛰️")
        
        # LoRa seri portunu aç
        try:
            self.lora_serial = serial.Serial(
                LORA_PORT, 
                LORA_BAUDRATE, 
                timeout=0.5,  # 2 saniyede bir okuma için daha uzun timeout
                write_timeout=1.0
            )
            self.lora_serial.reset_input_buffer()  # Buffer'ı temizle
            self.lora_serial.reset_output_buffer()
            self.get_logger().info(f"✓ LoRa seri portu açıldı: {LORA_PORT} ({LORA_BAUDRATE} baud)")
        except serial.SerialException as e:
            self.get_logger().error(f"✗ LoRa seri portu açılamadı: {e}")
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
        # ROS2 Publisher (Robot Kontrolü için)
        # =======================================================
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.target_lin = 0.0
        self.target_ang = 0.0
        self.twist_msg = Twist()
        
        # =======================================================
        # Launch Process Yönetimi
        # =======================================================
        self.robot_launch_process = None
        self.test_launch_process = None
        
        # =======================================================
        # Veri Buffer (Ethernet'ten gelen veriler için)
        # =======================================================
        self.data_buffer = []
        self.buffer_lock = threading.Lock()
        # Sıralı LoRa: karşıdan mesaj (komut tam içeriği) gelene kadar yeni mesaj göndermiyoruz
        self.lora_waiting_reply = False
        
        # =======================================================
        # Timer'lar
        # =======================================================
        # LoRa işlemleri için timer (2 saniyede bir: önce oku, sonra gönder)
        self.lora_timer = self.create_timer(LORA_INTERVAL, self.lora_cycle_callback)
        
        # TCP bağlantısını yönetmek için timer
        self.tcp_timer = self.create_timer(0.5, self.tcp_accept_callback)
        self.client_socket = None
        self.client_file = None
        
        # TCP okuma thread'i
        self.tcp_thread = None
        self.tcp_running = True
        self.start_tcp_thread()
        
        self.get_logger().info("Tüm özellikler başlatıldı. Sistem hazır.")
    
    def cleanup(self):
        """Kaynakları temizle"""
        # TCP thread'ini durdur
        self.tcp_running = False
        
        if self.client_file:
            try:
                self.client_file.close()
            except:
                pass
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        
        if self.lora_serial and self.lora_serial.is_open:
            try:
                self.lora_serial.close()
            except:
                pass
        
        # Launch process'leri durdur
        if self.robot_launch_process and self.robot_launch_process.poll() is None:
            self.robot_launch_process.terminate()
        
        if self.test_launch_process and self.test_launch_process.poll() is None:
            self.test_launch_process.terminate()
    
    def send_to_lora(self, data):
        """Veriyi LoRa üzerinden gönder (ham string; genelde JSON string)."""
        try:
            data_bytes = (data + '\n').encode('utf-8')
            self.lora_serial.write(data_bytes)
            self.lora_serial.flush()
            self.get_logger().info(f'[LoRa TX] {data[:80]}...')
            return True
        except serial.SerialException as e:
            self.get_logger().error(f"✗ LoRa gönderme hatası: {e}")
            return False
    
    def start_tcp_thread(self):
        """TCP okuma thread'ini başlat"""
        self.tcp_thread = threading.Thread(target=self.tcp_read_loop, daemon=True)
        self.tcp_thread.start()
    
    def tcp_read_loop(self):
        """TCP okuma döngüsü (ayrı thread'de çalışır)"""
        while self.tcp_running and rclpy.ok():
            try:
                if self.client_socket is None:
                    # Yeni bağlantı bekle
                    try:
                        self.client_socket, client_addr = self.tcp_socket.accept()
                        self.get_logger().info(f"✓ TCP bağlantı kabul edildi: {client_addr}")
                        self.client_file = self.client_socket.makefile('r', encoding='utf-8')
                    except socket.timeout:
                        time.sleep(0.1)
                        continue
                    except Exception as e:
                        self.get_logger().error(f"✗ TCP bağlantı hatası: {e}")
                        time.sleep(1)
                        continue
                
                # Bağlı istemciden veri oku
                try:
                    line = self.client_file.readline()
                    if line:
                        line = line.strip()
                        if line:
                            self.get_logger().info(f"[TCP RX] {line[:80]}...")
                            # Veriyi buffer'a ekle (2 saniyede bir LoRa'ya gönderilecek)
                            with self.buffer_lock:
                                self.data_buffer.append(line)
                    elif not line:
                        # Bağlantı kapandı
                        raise ConnectionError("Bağlantı kapandı")
                except (ConnectionError, OSError) as e:
                    # Bağlantı kapandı
                    self.get_logger().info(f"✗ TCP bağlantı kapandı")
                    if self.client_file:
                        try:
                            self.client_file.close()
                        except:
                            pass
                    if self.client_socket:
                        try:
                            self.client_socket.close()
                        except:
                            pass
                    self.client_socket = None
                    self.client_file = None
                    time.sleep(0.5)
                except Exception as e:
                    self.get_logger().error(f"✗ TCP okuma hatası: {e}")
                    time.sleep(0.1)
            except Exception as e:
                self.get_logger().error(f"✗ TCP döngü hatası: {e}")
                time.sleep(1)
    
    def tcp_accept_callback(self):
        """TCP timer callback (şu an kullanılmıyor, thread kullanıyoruz)"""
        pass
    
    def lora_cycle_callback(self):
        """Her 1 saniyede bir: önce LoRa'dan oku (karşıdan gelen mesaj), sonra buffer'dan tek mesaj gönder (karşıdan mesaj gelmeden gönderme)."""
        # 1. Önce LoRa'dan oku (Ubuntu'dan gelen komut veya herhangi bir mesaj)
        self.read_from_lora()
        # 2. Karşıdan mesaj gelene kadar yeni mesaj gönderme
        if self.lora_waiting_reply:
            return
        # 3. Buffer'dan tek mesajı JSON string olarak gönder
        self.send_from_buffer()
    
    def read_from_lora(self):
        """LoRa'dan gelen mesajı oku: karşıdan gelen herhangi bir mesaj sıradaki gönderime izin verir; komut ise işle."""
        if self.lora_serial.in_waiting > 0:
            try:
                msg = self.lora_serial.readline().decode('utf-8', errors='ignore').strip()
                if not msg:
                    return
                self.get_logger().info(f"📨 LoRa RX: {msg[:60]}...")
                # Sıralı protokol: karşıdan mesaj geldi, artık yeni mesaj gönderebiliriz
                self.lora_waiting_reply = False
                # Robot hareket komutları
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
                
                # Twist mesajı oluştur ve yayınla
                self.twist_msg.linear.x = self.target_lin
                self.twist_msg.angular.z = self.target_ang
                self.cmd_vel_pub.publish(self.twist_msg)
                
                # Launch komutları
                if msg == "robot_launch":
                    self.start_robot_launch(["ros2", "launch", "turtlebot3_bringup", "robot.launch.py"])
                elif msg == "rota_testi":
                    self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "rota_test.launch.py"])
                elif msg == "roaming_testi":
                    self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "roaming_test.launch.py"])
                elif msg == "steering_testi":
                    self.start_test_launch(["ros2", "launch", "turtlebot3_tests", "steering_test.launch.py"])
                elif msg == "testi_bitir":
                    self.stop_test_launch()
            
            except Exception as e:
                self.get_logger().warn(f"✗ LoRa okuma hatası: {e}")
    
    def send_from_buffer(self):
        """Buffer'daki en son veriyi 240 byte sınırına uygun kısa JSON olarak LoRa'ya gönder."""
        if self.lora_waiting_reply:
            return
        with self.buffer_lock:
            if not self.data_buffer:
                return
            data_line = self.data_buffer[-1]
            self.data_buffer.clear()
        try:
            obj = parse_windows_status_line(data_line)
            compact = compact_status_for_lora(obj)
            json_str = json.dumps(compact, ensure_ascii=False)
            # LoRa 240 byte sınırı: payload + \n dahil 240'ı geçmesin
            max_payload = LORA_MAX_BYTES - 1  # 1 = newline
            while len(json_str.encode("utf-8")) > max_payload and "i" in compact:
                # SSID'yi kısalt (i alanı)
                compact["i"] = compact["i"][:-1] if len(compact["i"]) > 1 else ""
                json_str = json.dumps(compact, ensure_ascii=False)
                if not compact["i"]:
                    break
        except Exception as e:
            self.get_logger().warn(f"JSON dönüşüm hatası, ham gönderim: {e}")
            max_payload = LORA_MAX_BYTES - 1
            b = data_line.encode("utf-8")
            json_str = b[:max_payload].decode("utf-8", errors="ignore") if len(b) > max_payload else data_line
        self.send_to_lora(json_str)
        self.lora_waiting_reply = True
    
    def start_robot_launch(self, cmd):
        """Robot launch dosyasını başlat"""
        if self.robot_launch_process is not None:
            if self.robot_launch_process.poll() is None:
                self.get_logger().info("Robot launch zaten çalışıyor. Dokunulmadı.")
                return
        
        self.get_logger().info("Robot launch başlatılıyor...")
        self.robot_launch_process = subprocess.Popen(cmd)
    
    def start_test_launch(self, cmd):
        """Test launch dosyasını başlat (önceki test'i durdur)"""
        if self.test_launch_process is not None:
            if self.test_launch_process.poll() is None:
                self.get_logger().warn("Önceki test launch durduruluyor...")
                self.test_launch_process.terminate()
                try:
                    self.test_launch_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.get_logger().warn("Test launch zorla öldürülüyor.")
                    self.test_launch_process.kill()
        
        self.get_logger().info("Yeni test launch başlatılıyor...")
        self.test_launch_process = subprocess.Popen(cmd)
    
    def stop_test_launch(self):
        """Test launch'ı durdur (arayüzden 'Testi Bitir' ile)."""
        if self.test_launch_process is None:
            return
        if self.test_launch_process.poll() is None:
            self.get_logger().info("Test launch durduruluyor...")
            self.test_launch_process.terminate()
            try:
                self.test_launch_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.test_launch_process.kill()
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
        print("\n🛑 Durduruldu (Ctrl+C)")
    except Exception as e:
        print(f"🛑 Hata: {e}")
    finally:
        if node is not None:
            node.on_shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
