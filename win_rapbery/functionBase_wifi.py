# -*- coding: utf-8 -*-
"""
Created on Fri Mar  3 10:41:59 2023
Updated on Tue Mar  3 14:30:00 2026

@author: samet
@updated: abdullah
"""

# %%
import sys
import time
from time import sleep, asctime
from pyfiglet import Figlet
from os import path, mkdir
import subprocess
import psutil
import socket

# Windows konsol encoding sorununu çöz
if sys.platform == 'win32':
    import os
    os.system('chcp 65001 >nul')  # UTF-8 konsol

DURATION = 5
SPACER = "\t|\t"

# %% Kanal-Frekans Mapping (Statik Veriler)
# 2.4 GHz Kanalları (1-14)
CHANNELS_2_4_GHZ = list(range(1, 15))

# 5 GHz Kanalları (UNII-1, UNII-2, UNII-2e, UNII-3)
CHANNELS_5_GHZ = [
    36, 40, 44, 48,  # UNII-1 (5.15-5.25 GHz)
    52, 56, 60, 64,  # UNII-2 (5.25-5.35 GHz)
    100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144,  # UNII-2e (5.47-5.725 GHz)
    149, 153, 157, 161, 165, 169, 173, 177  # UNII-3 (5.725-5.875 GHz)
]

# 6 GHz Kanalları (Wi-Fi 6E - UNII-5, UNII-6, UNII-7, UNII-8)
CHANNELS_6_GHZ = list(range(1, 234, 4))  # 1, 5, 9, 13, ... 233 (6 GHz band)

# %% Fonksiyon blogu
def readWlan():
    """netsh çıktısını okur. Hata durumunda boş liste döner."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return (result.stdout or "").split("\n")
    except (subprocess.TimeoutExpired, OSError, Exception):
        return []

def calculateRSSI(signalPercent):
    """
    Signal yüzdesinden RSSI hesaplar (tahmin). Bu bölüm, netsh çıktısında RSSI bilgisi bulunamadığında kullanılır.
    
    Args:
        signalPercent (int): Signal yüzdesi (0-100)
        
    Returns:
        str: Tahmini RSSI değeri (örn: "-55 dBm*")
    """
    try:
        # RSSI formülü: RSSI (dBm) = (Signal% / 2) - 100
        rssi_dbm = (signalPercent / 2) - 100
        return f"{rssi_dbm:.0f} dBm*"
    except Exception:
        return "N/A"


def getSignalInfo(sheelOutput):
    """
    netsh wlan show interfaces çıktısını parse eder.
    
    Returns:
        list: [BSSID, State, Signal%, RSSI, RxRate, TxRate, Channel, Band, RadioType, SSID]
    """
    if not sheelOutput:
        return []
    theList = []

    # BSSID
    for i in sheelOutput:
        if "BSSID" in i and "AP BSSID" in i:
            theList.append(":".join(i.split(":")[1:]))
            break
    
    # State
    for i in sheelOutput:
        if "State" in i:
            theList.append(i.split(":")[-1].strip())
            break
    
    # Signal (%)
    signal_value = ""
    signal_percent = 0
    for i in sheelOutput:
        if "Signal" in i and ":" in i:
            signal_value = i.split(":")[-1].strip()
            theList.append(signal_value)
            # Signal yüzdesini sayısal olarak sakla (RSSI hesaplaması için)
            try:
                signal_percent = int(signal_value.replace("%", "").strip())
            except:
                signal_percent = 0
            break
    
    # RSSI (dBm) - Önce netsh çıktısında "Rssi" satırını ara
    rssi_found = False
    for i in sheelOutput:
        # "Rssi" keyword'ünü ara (case-insensitive)
        if "Rssi" in i and ":" in i and "BSSID" not in i:
            rssi_raw = i.split(":")[-1].strip()
            # Format: "-33" -> "-33 dBm"
            theList.append(f"{rssi_raw} dBm")
            rssi_found = True
            break
    
    if not rssi_found:
        # RSSI bulunamadı, signal% değerinden hesapla
        if signal_percent > 0:
            theList.append(calculateRSSI(signal_percent))
        else:
            theList.append("N/A")
    
    # Receive rate
    for i in sheelOutput:
        if "Receive rate (Mbps)" in i:
            theList.append(i.split(":")[-1].strip())
            break

    # Transmit rate
    for i in sheelOutput:
        if "Transmit rate (Mbps)" in i:
            theList.append(i.split(":")[-1].strip())
            break

    # Channel
    channel_value = ""
    for i in sheelOutput:
        if "Channel" in i and ":" in i:
            channel_value = i.split(":")[-1].strip()
            theList.append(channel_value)
            break
    
    # Band - netsh'den almaya çalış, yoksa kanal bilgisinden hesapla
    band_found = False
    for i in sheelOutput:
        # "Band" keyword'ünü ara (bazı Windows versiyonlarında mevcut)
        if "Band" in i and ":" in i and "BSSID" not in i:
            band_value = i.split(":")[-1].strip()
            theList.append(band_value)
            band_found = True
            break
    
    if not band_found:
        # Band bilgisi yoksa, kanaldan hesapla ve '*' işareti ekle
        if channel_value:
            band_estimated = get_frequency_from_channel(channel_value, estimated=True)
            theList.append(band_estimated)
        else:
            theList.append("Unknown")

    # Radio type
    for i in sheelOutput:
        if "Radio type" in i:
            theList.append(i.split(":")[-1].strip())
            break
    
    # SSID
    for i in sheelOutput:
        if "SSID" in i and "BSSID" not in i and "AP" not in i:
            theList.append(i.split(":")[-1].strip())
            break
        
    return theList
    

def getSystemInfo():
    memoryUsage = psutil.virtual_memory()[2]
    cpuUsage = psutil.cpu_percent(0)
    
    return [str(cpuUsage), str(memoryUsage)]


def writeLogsToFile(log, filename):
    file = open("./logs/"+filename, "a", encoding='utf-8')
    file.writelines(log)
    file.close()


def getOneTimeInfo(wlanInfo, filename):
    
    log = "************************ Türk Telekom Wi-Fi State Tracker Logs *****************************\n\n"
    
    
    log += "\t\t\t\t\t\t************ Client Info *****************\n"
    log += ("\t\t\t\t\t\tInterface: ")
    
    for i in wlanInfo:
        if "Name" in i:
            log += (i.split(":")[-1].strip() + "\n")
            break
    
    log += ("\t\t\t\t\t\tWi-Fi Card: ")
    for i in wlanInfo:
        if "Description" in i:
            log += (i.split(":")[-1].strip() + "\n")
            break
            
    log += ("\t\t\t\t\t\tHWADDR(MAC): ")
    for i in wlanInfo:
        if "Physical address" in i:
            log += ":".join(i.split(":")[1:])
            break
            
    log += "\n\n\t\t\t\t\t\t************ DUT Info ********************\n"
    
    log += ("\t\t\t\t\t\tSSID: ")
    for i in wlanInfo:
        if "SSID" in i:
            log += (i.split(":")[-1].strip() + "\n")
            break
    
    log += ("\t\t\t\t\t\tBSSID: ")
    for i in wlanInfo:
        if "BSSID" in i:
            log += ":".join(i.split(":")[1:])
            break
        
    log += "\n\n\t\t\t\t\t\t******************************************\n"
        
    
    log += "\n\n****************************** Periyodik Data Blogu ***************************************\n\n"
    
    log += "----- Time | State, BSSID, Signal Level, RSSI, Receive Rate, Transmit Rate, Channel, Band, 802.11x, SSID | CPU Usage, RAM Usage\n\n"
    
    writeLogsToFile(log, filename)
    print(log)
    
    
def initialIO():
    custom_fig = Figlet()
    
    print("*"*95)  
    print(custom_fig.renderText("            Türk Telekom"))
    print(custom_fig.renderText("            Wi-Fi Tracker"))
    print("Wi-Fi State Tracker v0.2 - Samet Özabacı" + "\t"*4 + "  © Türk Telekom - 2026")
    #print("\t"*6 + "v0.2 - © Turk Telekom - 2026 by Samet Özabacı\n")
    print("*"*95)  
    
    brand = input("Cihazın Markası: ")    
    model = input("Cihazın Modeli: ")    
    firmware = input("Cihazın Firmware'i: ")
    duration = int(input("Test Suresi(sn): "))
    print("")
    
    if not path.isdir("logs"):
        mkdir("logs")
        
    return [brand, model, firmware, duration]


def createFileName(inputs):
    return "wifiAnaliz_" + inputs[0] + "_" + inputs[1] + "_" + inputs[2] + "_" + str(inputs[3]) + "sn_log.txt"
    
    

def get_frequency_from_channel(channel, estimated=False):
    """
    Kanal numarasından frekans bandını döndürür. Bu bölüm, netsh çıktısında Band bilgisi bulunamadığında kullanılır.
    
    Args:
        channel (str veya int): Kanal numarası
        estimated (bool): True ise sonuna '*' ekler (tahmin edildiğini gösterir)
        
    Returns:
        str: "2.4 GHz", "5 GHz", "6 GHz", "2.4 GHz*" veya "Unknown"
    """
    try:
        channel_num = int(channel)
        
        if channel_num in CHANNELS_2_4_GHZ:
            freq = "2.4 GHz"
        elif channel_num in CHANNELS_5_GHZ:
            freq = "5 GHz"
        elif channel_num in CHANNELS_6_GHZ:
            freq = "6 GHz"
        else:
            freq = "Unknown"
        
        # Tahmin edilmişse sonuna '*' ekle
        if estimated and freq != "Unknown":
            freq += "*"
        
        return freq
    except (ValueError, TypeError):
        return "Unknown"


def compare_mac_for_band_steering(mac1, mac2):
    """
    İki MAC adresini band steering için karşılaştırır.
    Band steering: İlk 4 byte (OUI + cihaz prefix) aynı, son 2 byte değişebilir.
    
    MAC Format: XX:XX:XX:XX:XX:XX (6 byte)
    - İlk 4 byte aynıysa -> Band Steering (aynı cihazın farklı radyoları)
    - İlk 4 byte farklıysa -> Roaming (farklı cihaz)
    
    Args:
        mac1 (str): İlk MAC adresi (örn: "4c:2e:fe:34:8a:cf")
        mac2 (str): İkinci MAC adresi
        
    Returns:
        bool: Band steering ise True, değilse False
    """
    try:
        # Boşlukları temizle ve küçük harfe çevir
        mac1 = mac1.strip().lower()
        mac2 = mac2.strip().lower()
        
        # Aynı MAC ise False
        if mac1 == mac2:
            return False
        
        # İlk 4 byte'ı karşılaştır (format: "4c:2e:fe:34")
        # İlk 14 karakter: "XX:XX:XX:XX:" (4 byte + 3 colon + son colon)
        mac1_prefix = mac1[:14]  # "4c:2e:fe:34:"
        mac2_prefix = mac2[:14]  # "4c:2e:fe:34:"
        
        # İlk 4 byte aynıysa Band Steering
        return mac1_prefix == mac2_prefix
    except Exception:
        return False


def detect_wifi_event(current_data, previous_data=None):
    """
    WiFi event'lerini tespit eder (Band Steering veya Roaming).
    
    Event Tipleri:
    - 0: Event yok
    - 1: Band Steering tespit edildi
    - 2: Roaming tespit edildi
    - -1: Hata tespit edildi
    
    Args:
        current_data (list): Mevcut WiFi durumu [BSSID, State, Signal%, RSSI, RxRate, TxRate, Channel, Band, RadioType, SSID]
        previous_data (list, optional): Bir önceki WiFi durumu
        
    Returns:
        tuple: (event_code, event_message)
            - event_code (int): Event kodu
            - event_message (str): Event mesajı (varsa)
    """
    # İlk çalıştırmada veya önceki data yoksa
    if previous_data is None or len(previous_data) < 10:
        return (0, None)
    
    # Data validation
    if len(current_data) < 10:
        return (-1, "ERROR: Insufficient data")
    
    try:
        # Current data (yeni format: 10 element)
        current_bssid = current_data[0].strip()
        current_state = current_data[1].strip().lower()
        current_rssi = current_data[3].strip()
        current_channel = current_data[6].strip()
        current_band = current_data[7].strip()
        current_ssid = current_data[9].strip()
        
        # Previous data
        prev_bssid = previous_data[0].strip()
        prev_state = previous_data[1].strip().lower()
        prev_rssi = previous_data[3].strip()
        prev_channel = previous_data[6].strip()
        prev_band = previous_data[7].strip()
        prev_ssid = previous_data[9].strip()
        
        # Bağlantı yoksa veya disconnected ise event kontrolü yapma
        if current_state != "connected" or prev_state != "connected":
            return (0, None)
        
        # MAC adresi aynı ise event yok
        if current_bssid == prev_bssid:
            return (0, None)
        
        # Band Steering kontrolü: İlk 4 byte aynı (aynı cihazın farklı radyosu)
        if compare_mac_for_band_steering(prev_bssid, current_bssid):
            event_msg = f"@@@@@ EVENT DETECTED: Band Steering occurred at {asctime()}\n"
            event_msg += f"        From: {prev_band} (Ch {prev_channel}, {prev_bssid}, RSSI: {prev_rssi})\n"
            event_msg += f"        To:   {current_band} (Ch {current_channel}, {current_bssid}, RSSI: {current_rssi})\n"
            event_msg += f"        SSID: {current_ssid}"
            return (1, event_msg)
        
        # Roaming kontrolü: İlk 4 byte farklı (farklı AP/cihaz)
        else:
            freq_change = ""
            # Band değişimi kontrolü (tahmin işaretlerini temizleyerek karşılaştır)
            prev_band_clean = prev_band.replace("*", "")
            current_band_clean = current_band.replace("*", "")
            
            if current_band_clean != prev_band_clean:
                freq_change = f"Frequency changed from {prev_band} to {current_band}"
            else:
                freq_change = f"Same frequency ({current_band})"
            
            event_msg = f"@@@@@ EVENT DETECTED: Roaming occurred at {asctime()}\n"
            event_msg += f"        From: {prev_bssid} (Ch {prev_channel}, {prev_band}, RSSI: {prev_rssi})\n"
            event_msg += f"        To:   {current_bssid} (Ch {current_channel}, {current_band}, RSSI: {current_rssi})\n"
            event_msg += f"        {freq_change}, SSID: {current_ssid}"
            return (2, event_msg)
    
    except Exception as e:
        return (-1, f"ERROR: {str(e)}")


def printSummary(duration, band_steering_count, roaming_count, filename):
    """
    Test sonunda özet bilgileri yazdırır.
    
    Args:
        duration (int): Test süresi (saniye)
        band_steering_count (int): Tespit edilen band steering sayısı
        roaming_count (int): Tespit edilen roaming sayısı
        filename (str): Log dosya adı
    """
    summary = "\n\n"
    summary += "="*100 + "\n"
    summary += " "*35 + "TEST SUMMARY / TEST ÖZETI\n"
    summary += "="*100 + "\n\n"
    
    summary += f"  ⏱️  Test Duration (Test Süresi)              : {duration} seconds ({duration // 60} min {duration % 60} sec)\n"
    summary += f"  📊  Total Events Detected (Toplam Event)     : {band_steering_count + roaming_count}\n"
    summary += f"  🔄  Band Steering Events                     : {band_steering_count}\n"
    summary += f"  🌐  Roaming Events                           : {roaming_count}\n\n"
    
    if band_steering_count + roaming_count == 0:
        summary += "  ℹ️  No events detected during the test period.\n"
        summary += "     (Test süresi boyunca hiçbir event tespit edilmedi.)\n\n"
    elif duration > 0:
        summary += f"  📈  Event Rate (Olay Oranı)                  : {((band_steering_count + roaming_count) / duration * 60):.2f} events/minute\n\n"
    
    summary += "="*100 + "\n"
    summary += " "*30 + "End of Test - Test Tamamlandı\n"
    summary += "="*100 + "\n"
    
    print(summary)
    writeLogsToFile(summary, filename)


def getPeriodicData(duration, filename):
    
    logString = "----- "
    previous_signal_data = None  # Önceki WiFi durumunu sakla
    
    # Event sayaçları
    band_steering_count = 0
    roaming_count = 0
    
    for i in range(duration):
        currentTime = asctime()    
        logString += (currentTime + SPACER)
        
        signal = getSignalInfo(readWlan())
        for i in signal:
            logString += (str(i) + ", ")
        logString = logString[:-2]
        logString += SPACER
    
        systemInfo = getSystemInfo()
        for i in systemInfo:
            logString += (str(i) + "%, ")
        logString = logString[:-2]
        logString += "\n"
        
        print(logString)
        writeLogsToFile(logString, filename)
        
        # Event detection
        event_code, event_message = detect_wifi_event(signal, previous_signal_data)
        
        if event_code == 1:
            # Band Steering tespit edildi
            band_steering_count += 1
            event_log = "        " + event_message + "\n\n"
            print(event_log)
            writeLogsToFile(event_log, filename)
        elif event_code == 2:
            # Roaming tespit edildi
            roaming_count += 1
            event_log = "        " + event_message + "\n\n"
            print(event_log)
            writeLogsToFile(event_log, filename)
        elif event_code == -1:
            # Hata durumu
            error_log = "        @@@@@ ERROR: " + event_message + "\n\n"
            print(error_log)
            writeLogsToFile(error_log, filename)
        
        # Mevcut durumu sakla
        previous_signal_data = signal.copy()
        
        sleep(1)
        
        logString = "----- "
    
    # Test tamamlandı, özet yazdır
    printSummary(duration, band_steering_count, roaming_count, filename)


class WifiStatusTcpSender:
    """
    Wi-Fi durumunu toplar, tek satır string yapar, TCP ile Raspberry'ye gönderir.
    log_file verilirse her satır dosyaya da yazılır.
    """
    def __init__(self, server_ip='192.168.1.11', server_port=5001, interval=1.0, log_file=None):
        self.server_ip = server_ip
        self.server_port = server_port
        self.interval = interval
        self.log_file = log_file
        self.socket = None
        self.previous_signal_data = None
    
    def connect(self):
        if self.socket is not None:
            return
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.server_ip, self.server_port))
            print(f"[Bağlı] Sunucuya bağlandı: {self.server_ip}:{self.server_port}")
        except Exception as e:
            print(f"Bağlantı hatası: {e}")
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
            self.socket = None
    
    def close(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None
    
    def build_status_line(self):
        """Wi-Fi + CPU/RAM bilgisini tek satır string yapar."""
        # Wi-Fi durumu
        wlan_lines = readWlan()
        signal_info = getSignalInfo(wlan_lines)
        # signal_info: [BSSID, State, Signal%, RSSI, RxRate, TxRate, Channel, Band, RadioType, SSID]
        if len(signal_info) < 10:
            # Beklenen formatta değilse, basit bir hata mesajı döndür
            return f"{asctime()} | ERROR: Wi-Fi bilgisi okunamadı"
        
        # Sistem durumu
        cpu_usage, ram_usage = getSystemInfo()
        
        # Event tespiti (band steering=1, roaming=2)
        event_code, _ = detect_wifi_event(signal_info, self.previous_signal_data)
        
        # Son durumu sakla
        self.previous_signal_data = signal_info.copy()
        
        bssid, state, signal_percent, rssi, rx_rate, tx_rate, channel, band, radio_type, ssid = signal_info
        
        parts = [
            f"time={asctime()}",
            f"state={state.strip()}",
            f"ssid={ssid.strip()}",
            f"bssid={bssid.strip()}",
            f"signal={signal_percent}",
            f"rssi={rssi}",
            f"rx={rx_rate} Mbps",
            f"tx={tx_rate} Mbps",
            f"channel={channel}",
            f"band={band}",
            f"radio={radio_type}",
            f"cpu={cpu_usage}%",
            f"ram={ram_usage}%",
        ]
        
        if event_code in (1, 2):
            parts.append(f"event={event_code}")  # 1=BandSteering, 2=Roaming
        
        return " | ".join(parts)
    
    def send_status_once(self):
        self.connect()
        try:
            status_line = self.build_status_line()
            print(status_line)
            if self.socket is not None:
                self.socket.sendall((status_line + "\n").encode("utf-8"))
            if self.log_file:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(status_line + "\n")
        except Exception as e:
            print(f"Hata: {e}")
            self.close()
    
    def run_loop(self, duration=None):
        """duration=None ise Ctrl+C'ye kadar çalışır; sayı verilirse o kadar saniye çalışır."""
        max_iterations = None
        if duration is not None and self.interval > 0:
            max_iterations = max(1, int(duration / self.interval))
        next_tick = time.monotonic()
        iteration = 0
        try:
            while True:
                self.send_status_once()
                iteration += 1
                if max_iterations is not None and iteration >= max_iterations:
                    break
                next_tick += self.interval
                sleep_time = next_tick - time.monotonic()
                if sleep_time > 0:
                    sleep(sleep_time)
        except KeyboardInterrupt:
            print("\nDurduruldu (Ctrl+C).")
        finally:
            self.close()


if __name__ == "__main__":
    # Windows'ta çalıştır: Wi-Fi bilgisini alır, 1 sn'de bir TCP ile Raspberry'ye gönderir.
    sender = WifiStatusTcpSender(server_ip='192.168.1.11', server_port=5001, interval=1.0)
    sender.run_loop(duration=None)  # Ctrl+C ile durdur