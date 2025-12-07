# LoRa Tabanlı Robotik Test Sistemi

## 🚀 Proje Hakkında

Bu proje, LoRa teknolojisi kullanarak uzun menzilli iletişim sağlayan mobil robot sistemlerini geliştirmeyi ve robotun otonom görev yürütme kapasitesini test etmeyi amaçlamaktadır.

## 🔐 Admin Paneli Erişimi

### Admin Giriş Bilgileri:
- **URL**: http://127.0.0.1:8000/admin/
- **Kullanıcı Adı**: `admin`
- **Şifre**: `turktelekom`

### Robot Kontrol Paneli:
- **URL**: http://127.0.0.1:8000/robot/
- **Login**: http://127.0.0.1:8000/robot/login/

### Login Kullanıcısı:
- **Kullanıcı Adı**: `admin`
- **Şifre**: `turktelekom`

## 🛠️ Kurulum

### Gereksinimler:
- Python 3.8+
- PostgreSQL
- LoRa Modülü (E22 900T22D)

### Kurulum Adımları:
```bash

# Bağımlılıkları yükle
pip install -r requirements.txt

# Veritabanı migration'larını uygula
python3 manage.py migrate

# Sunucuyu başlat
python3 manage.py runserver
```

## 📡 LoRa Modülü Bağlantısı

LoRa modülünüzü `/dev/ttyUSB0` portuna bağlayın. Farklı bir port kullanıyorsanız, `lora_client.py` dosyasındaki port ayarını değiştirin.

```pythonS
# lora_client.py içinde
lora_client = LoRaClient(port='/dev/ttyUSB0', baudrate=115200)
```

## 📊 Veritabanı

### PostgreSQL Ayarları:
- **Veritabanı**: `wifi_tester`
- **Kullanıcı**: `abdullah`
- **Şifre**: `a`
- **Host**: `localhost`
- **Port**: `5432`

## 🔧 Önemli Notlar

### Admin Şifresi:
- **Kullanıcı**: `admin`
- **Şifre**: `turktelekom`

## 📁 Proje Yapısı

```
test_server/
├── cmd_vel_web/
│   ├── robot_control/          # Ana uygulama
│   │   ├── lora_client.py     # LoRa iletişim modülü
│   │   ├── views.py           # Django view'ları
│   │   └── models.py          # Veritabanı modelleri
│   ├── cmd_vel_web/           # Django projesi
│   ├── static/                # Statik dosyalar
│   └── templates/             # HTML şablonları
├── requirements.txt           # Python bağımlılıkları
└── README.md                 # Bu dosya
```

## 🎯 Özellikler

- ✅ LoRa tabanlı uzun menzilli iletişim
- ✅ Robot kontrol arayüzü
- ✅ Gerçek zamanlı sensör veri toplama
- ✅ IMU sensörleri ile hareket algılama
- ✅ PostgreSQL veritabanı
- ✅ Admin paneli
- ✅ Kullanıcı yönetimi

## 🔬 Teknolojik Özellikler

- **LoRa İletişimi**: Uzun menzilli, düşük güç tüketimli iletişim
- **Web Tabanlı Kontrol**: Django ile geliştirilmiş modern web arayüzü
- **Gerçek Zamanlı Veri**: IMU sensörleri, Lidar ve robot durumu takibi
- **Mobil Kontrol**: İleri, geri, sağ, sol hareket komutları
- **Sensör Verileri**: RSSI, pil durumu, mesafe ve konum bilgileri

## 👥 Proje Ekibi

- **Elif Aykırı** - Fizik Mühendisliği
- **Abdullah Saki** - Elektrik-Elektronik Mühendisliği  
- **Kerem Odabaş** - Elektrik-Elektronik Mühendisliği
- **Sümeyra Şimşek** - Elektrik-Elektronik Mühendisliği
- **Şevin Kaya** - Elektrik-Elektronik Mühendisliği

## 🎓 Akademik Danışmanlar

- **Akademik Danışman**: Dr. Öğr. Üyesi Haluk Bayram
- **Sanayi Danışmanı**: Samet Özabacı (Türk Telekom)

## 📋 Proje Bilgileri

- **Proje Başlığı**: Robotik WiFi Test Sİstemi
- **Destek Programı**: 2209-B - Üniversite Öğrencileri Sanayiye Yönelik Araştırma Projeleri Desteği Programı
- **Yürütüleceği Kurum**: Türk Telekom
- **Proje Süresi**: 12 Ay

## 📄 Lisans

Bu proje TÜBİTAK 2209-B programı kapsamında geliştirilmiştir.
