# robot_control/views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from .lora_client import lora_client

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
    """LoRa'dan gelen son mesajı döndürür"""
    last_message = lora_client.get_last_message()
    return JsonResponse({'status': 'success', 'message': last_message})
