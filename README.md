# LoRa Tabanlı Robotik Test Sistemi

## Proje Hakkında

Bu proje, LoRa teknolojisi ile uzun menzilli iletişim sağlayarak mobil robot sistemini kontrol etmeyi ve robotun otonom görev yürütme yeteneğini kullanarak WiFi testlerinin otonom olarak yapılmasını amaçlamaktadır.

## Admin Paneli Erişimi

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

## Kurulum

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

# Superuser (yönetici) kullanıcısı oluştur
python3 manage.py createsuperuser

# Sunucuyu başlat
python3 manage.py runserver
```

## LoRa Modülü Bağlantısı

LoRa modülünüzü `/dev/ttyUSB0` portuna bağlayın. Farklı bir port kullanıyorsanız, `lora_client.py` dosyasındaki port ayarını değiştirin.

```pythonS
# lora_client.py içinde
lora_client = LoRaClient(port='/dev/ttyUSB0', baudrate=115200)
```

## Veritabanı

### PostgreSQL Ayarları:
- **Veritabanı**: `wifi_tester`
- **Kullanıcı**: `abdullah`
- **Şifre**: `a`
- **Host**: `localhost`
- **Port**: `5432`

## Önemli Notlar

### Admin Şifresi:
- **Kullanıcı**: `admin`
- **Şifre**: `turktelekom`

## Proje Yapısı

```
test_server/
├── cmd_vel_web/                    # Django proje klasörü
│   ├── cmd_vel_web/                # Django proje ayarları
│   │   ├── __init__.py
│   │   ├── settings.py            # Proje ayarları
│   │   ├── urls.py                # Ana URL yapılandırması
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── manage.py                   # Django yönetim scripti
│   ├── db.sqlite3                  # SQLite veritabanı
│   └── robot_control/              # Ana Django uygulaması
│       ├── __init__.py
│       ├── admin.py                # Admin panel ayarları
│       ├── models.py               # Veritabanı modelleri
│       ├── views.py                # Django view'ları
│       ├── urls.py                 # Uygulama URL'leri
│       ├── lora_client.py          # LoRa iletişim modülü
│       ├── migrations/             # Veritabanı migration'ları
│       ├── static/
│       │   └── robot_control/
│       │       └── images/
│       │           └── ttkom_logo.svg
│       └── templates/
│           ├── registration/
│           │   └── kullanici_giris.html
│           └── robot_control/
│               └── robot_kontrol_paneli.html
├── requirements.txt                # Python bağımlılıkları
└── README.md                       # Proje dokümantasyonu
```

## Özellikler

- LoRa tabanlı uzun menzilli iletişim
- Web tabanlı robot kontrol arayüzü
- Gerçek zamanlı sensör veri toplama (IMU, Lidar, RSSI, pil durumu)
- Mobil kontrol (ileri, geri, sağ, sol hareket komutları)
- PostgreSQL veritabanı
- Admin paneli ve kullanıcı yönetimi

## Proje Ekibi

- **Elif Aykırı** - Fizik Mühendisliği
- **Abdullah Saki** - Elektrik Elektronik Mühendisliği  
- **Kerem Odabaş** - Elektrik Elektronik Mühendisliği
- **Şevin Kaya** - Elektrik Elektronik Mühendisliği

## Akademik Danışmanlar

- **Akademik Danışman**: Doç. Dr. Haluk Bayram
- **Sanayi Danışmanı**: Dr. ad. Samet Özabacı (Türk Telekom)

## Proje Bilgileri

- **Proje Başlığı**: Robotik WiFi Test Sİstemi
- **Destek Programı**: 2209-B - Üniversite Öğrencileri Sanayiye Yönelik Araştırma Projeleri Desteği Programı
- **Yürütüleceği Kurum**: Türk Telekom
- **Proje Süresi**: 12 Ay

## Lisans

Bu proje TÜBİTAK 2209-B programı kapsamında geliştirilmiştir.
