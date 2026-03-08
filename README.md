# LoRa Tabanlı Robotik WiFi Test Sistemi

## Proje Hakkında

Bu proje, LoRa teknolojisi ile uzun menzilli iletişim kullanarak mobil robot sistemini kontrol etmeyi ve robotun otonom görev yürütme yeteneğiyle WiFi testlerinin otonom yapılmasını amaçlamaktadır. Sistem üç katmandan oluşur: **Windows PC** (Wi-Fi verisi), **Raspberry Pi** (köprü + ROS2 robot), **Ubuntu laptop** (web arayüzü).

---

## Sistem Mimarisi

```
[Windows PC]  ---- TCP (Ethernet) ---->  [Raspberry Pi]  ---- LoRa (seri) ---->  [Ubuntu Laptop]
     |                    |                        |                                  |
  Wi-Fi durumu        Port 5001              JSON (Wi-Fi) / Komutlar            Web arayüzü
  (key=value satır)   Raspberry IP           ww, ss, robot_launch, testler       /robot/
                     (192.168.1.11)         /dev/ttyAMA0 9600                   /dev/ttyUSB0 9600
```

- **Windows:** Wi-Fi durumunu toplar, TCP ile Raspberry’ye satır satır gönderir.
- **Raspberry Pi:** TCP’den gelen veriyi JSON’a çevirip LoRa ile Ubuntu’ya gönderir; LoRa’dan gelen komutlarla robotu (ROS2 `/cmd_vel`) ve test launch’larını yönetir. Sıralı protokol: karşıdan mesaj gelene kadar yeni mesaj göndermez.
- **Ubuntu:** Django web arayüzü; LoRa ile Raspberry’den Wi-Fi JSON alır, komut gönderir (hareket, robot başlat, test başlat/bitir). İletişim reset butonu ile kilitlenme çözülür.

Detaylı iletişim ve mesaj uyumu için: **[ILETISIM_VE_MESAJ_RAPORU.md](ILETISIM_VE_MESAJ_RAPORU.md)**

---

## Hızlı Erişim

### Robot Kontrol Paneli
- **URL:** http://127.0.0.1:8000/robot/
- **Giriş:** http://127.0.0.1:8000/robot/login/
- **Kullanıcı:** `admin` / **Şifre:** `turktelekom`

### Admin Paneli
- **URL:** http://127.0.0.1:8000/admin/
- **Kullanıcı:** `admin` / **Şifre:** `turktelekom`

---

## Kurulum ve Çalıştırma

### Gereksinimler
- Python 3.8+
- PostgreSQL (veya proje ayarına göre SQLite)
- LoRa modülü (E22 900T22D veya uyumlu); Raspberry’de `/dev/ttyAMA0`, Ubuntu’da `/dev/ttyUSB0`

### 1. Ubuntu – Web Arayüzü (cmd_vel_web)

```bash
pip install -r requirements.txt
cd cmd_vel_web
python manage.py migrate
python manage.py createsuperuser   # İlk kurulumda
python manage.py runserver
```

Tarayıcıda http://127.0.0.1:8000/robot/ adresine gidin. LoRa modülü USB’de ise `/dev/ttyUSB0` (9600 baud) kullanılır; yoksa uygulama dummy modda çalışır.

### 2. Raspberry Pi – LoRa Bridge (win_rapbery)

Raspberry’de ROS2 kurulu olmalı. Ethernet IP’yi 192.168.1.11 yapın (veya Windows tarafındaki `server_ip`’yi buna göre ayarlayın).

```bash
cd win_rapbery
# ROS2 ortamını aktive edin, ardından:
python3 raspberry_lora_bridge.py
```

- TCP sunucu: `0.0.0.0:5001`
- LoRa: `/dev/ttyAMA0`, 9600 baud

### 3. Windows PC – Wi-Fi Verisi (win_rapbery)

Windows’ta Python 3, Bağımlılıklar: `pip install -r requirements.txt` (psutil, pyfiglet dahil). Raspberry ile aynı ağda (Ethernet) ve Raspberry IP’si 192.168.1.11 olmalı.

```bash
cd win_rapbery
python functionBase_wifi.py
```

Veya sadece TCP gönderimi için:

```python
from functionBase_wifi import WifiStatusTcpSender
sender = WifiStatusTcpSender(server_ip='192.168.1.11', server_port=5001, interval=1.0)
sender.run_loop(duration=None)  # Ctrl+C ile durdur
```

---

## Proje Yapısı

```
test_server/
├── cmd_vel_web/                      # Django web projesi (Ubuntu)
│   ├── cmd_vel_web/                  # Ayarlar, urls
│   ├── manage.py
│   └── robot_control/                # Robot arayüzü uygulaması
│       ├── views.py                  # send_command, reset_communication, get_last_lora_message
│       ├── urls.py
│       ├── lora_client.py            # LoRa istemcisi (seri, sıralı protokol)
│       ├── templates/robot_control/
│       │   └── robot_kontrol_paneli.html
│       └── static/
├── win_rapbery/                      # Windows + Raspberry kodları
│   ├── functionBase_wifi.py          # Windows: Wi-Fi okuma, TCP gönderimi (WifiStatusTcpSender)
│   └── raspberry_lora_bridge.py      # Raspberry: TCP sunucu, LoRa köprü, ROS2 cmd_vel
├── ILETISIM_VE_MESAJ_RAPORU.md       # İletişim ve mesaj formatları detay raporu
├── requirements.txt
└── README.md
```

---

## LoRa ve Port Ayarları

| Cihaz      | Seri port       | Baudrate | Amaç                    |
|------------|-----------------|----------|-------------------------|
| Raspberry  | `/dev/ttyAMA0`  | 9600     | Ubuntu ile sıralı iletişim |
| Ubuntu     | `/dev/ttyUSB0`  | 9600     | Arayüz → Raspberry komutları, Wi-Fi JSON alımı |

Farklı port kullanıyorsanız:
- **Ubuntu:** `cmd_vel_web/robot_control/lora_client.py` içinde `LoRaClient('/dev/ttyUSB0', 9600)` satırını güncelleyin.
- **Raspberry:** `win_rapbery/raspberry_lora_bridge.py` içinde `LORA_PORT` ve `LORA_BAUDRATE` değişkenlerini güncelleyin.

---

## Arayüz Özellikleri

- **Manuel kontrol:** İleri, geri, sol, sağ, dur (ww, xx, aa, dd, ss)
- **Robot başlat:** ROS2 robot launch
- **Testler:** Rota / Roaming / Steering testi başlat, Testi Bitir
- **LoRa mesajı:** Son gelen mesaj (ham) ve ham veri geçmişi
- **İletişim reset:** Karşıdan cevap gelmeden tek seferlik mesaj gönderir; kilitlenme durumunda kullanılır

---

## Veritabanı (Django)

Proje SQLite veya PostgreSQL kullanabilir. Ayarlar `cmd_vel_web/cmd_vel_web/settings.py` içindedir. Örnek PostgreSQL:

- **Veritabanı:** `wifi_tester`
- **Kullanıcı:** `abdullah`
- **Şifre:** `a`
- **Host:** `localhost`
- **Port:** `5432`

---

## Proje Ekibi

- **Elif Aykırı** – Fizik Mühendisliği
- **Abdullah Saki** – Elektrik-Elektronik Mühendisliği
- **Kerem Odabaş** – Elektrik-Elektronik Mühendisliği
- **Şevin Kaya** – Elektrik-Elektronik Mühendisliği

## Danışmanlar

- **Akademik Danışman:** Doç. Dr. Haluk Bayram
- **Sanayi Danışmanı:** Dr. ad. Samet Özabacı (Türk Telekom)

## Proje Bilgisi

- **Proje:** Robotik WiFi Test Sistemi
- **Program:** TÜBİTAK 2209-B – Üniversite Öğrencileri Sanayiye Yönelik Araştırma Projeleri
- **İş ortağı:** Türk Telekom
- **Süre:** 12 ay

## Lisans

Bu proje TÜBİTAK 2209-B programı kapsamında geliştirilmiştir.
