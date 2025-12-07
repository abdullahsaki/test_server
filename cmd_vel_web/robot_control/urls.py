# robot_control/urls.py
from django.urls import path
from . import views

app_name = 'robot_control'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('send_command/', views.send_command, name='send_command'),
]
