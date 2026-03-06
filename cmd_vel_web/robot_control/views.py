# robot_control/views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from .lora_client import lora_client
import os


def _format_lora_status(status: dict) -> str:
    """
    LoRa'dan gelen parse edilmiş Wi-Fi durumunu (dict) okunabilir tek satır string'e çevirir.
    Beklenen alanlar: time, state, ssid, bssid, signal, rssi, rx, tx, channel, band, radio, cpu, ram, event, win_batt, rpi_batt
    """
    if not status:
        return "-"

    time_str = status.get("time", "-")
    state = status.get("state", "-")
    ssid = status.get("ssid", "-")
    bssid = status.get("bssid", "-")
    signal = status.get("signal", "-")
    rssi = status.get("rssi", "-")
    rx = status.get("rx", "-")
    tx = status.get("tx", "-")
    channel = status.get("channel", "-")
    band = status.get("band", "-")
    radio = status.get("radio", "-")
    cpu = status.get("cpu", "-")
    ram = status.get("ram", "-")
    win_batt = status.get("win_batt")
    rpi_batt = status.get("rpi_batt")
    event = status.get("event")

    if event == "1":
        event_str = "Band Steering olayı"
    elif event == "2":
        event_str = "Roaming olayı"
    elif event:
        event_str = f"Olay kodu={event}"
    else:
        event_str = "Olay yok"

    batt_str = ""
    if win_batt or rpi_batt:
        batt_str = f" | Batarya (Win/RPi): {win_batt or '-'} / {rpi_batt or '-'}"

    readable = (
        f"Zaman: {time_str} | Durum: {state} | "
        f"SSID: {ssid} | BSSID: {bssid} | "
        f"Sinyal: {signal} ({rssi}) | Hız (Rx/Tx): {rx} / {tx} | "
        f"Kanal/Bant: {channel} / {band} | Standart: {radio} | "
        f"Windows CPU/RAM: {cpu} / {ram}{batt_str} | {event_str}"
    )
    return readable


def _log_lora_readable(text: str) -> None:
    """Okunabilir LoRa durumunu log dosyasına ekler."""
    if not text:
        return
    try:
        base_dir = getattr(settings, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "lora_readable.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        # Log yazılamazsa sessizce geç
        pass

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('robot_control:home')
        else:
            return render(request, 'registration/kullanici_giris.html', {
                'error': 'Kullanıcı adı veya şifre hatalı!',
                'username': username
            })
    return render(request, 'registration/kullanici_giris.html')

@csrf_exempt
def logout_view(request):
    logout(request)
    return redirect('/robot/login/')

@csrf_exempt
@login_required(login_url='robot_control:login')
def home(request):
    return render(request, 'robot_control/robot_kontrol_paneli.html', {
        'user': request.user
    })

@csrf_exempt
@login_required(login_url='robot_control:login')
def send_command(request):
    command = request.POST.get('command')
    if not command:
        return JsonResponse({'status': 'error', 'message': 'Komut gerekli'}, status=400)
    lora_client.send_command(command)
    return JsonResponse({'status': 'success', 'message': f'{command} komutu gönderildi'})

@csrf_exempt
@login_required(login_url='robot_control:login')
def reset_communication(request):
    """İletişim reset: cevap gelmemiş olsa bile karşıya bir mesaj gönderir (Raspberry beklemeden çıksın)."""
    ok = lora_client.reset_communication()
    return JsonResponse({'status': 'success' if ok else 'error', 'message': 'İletişim reset gönderildi' if ok else 'Port kapalı'})

@csrf_exempt
@login_required(login_url='robot_control:login')
def get_last_lora_message(request):
    """
    LoRa'dan gelen son ham mesajı ve varsa parse edilmiş okunabilir özetini döndürür.
    Ayrıca okunabilir özet log dosyasına yazılır.
    """
    last_message = lora_client.get_last_message()
    parsed_status = None
    try:
        parsed_status = lora_client.get_parsed_status()
    except Exception:
        parsed_status = None

    readable = _format_lora_status(parsed_status) if parsed_status else None
    if readable:
        _log_lora_readable(readable)

    return JsonResponse({'status': 'success', 'message': last_message, 'pretty': readable})
