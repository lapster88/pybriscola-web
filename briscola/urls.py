from django.urls import path

from . import views

urlpatterns = [
    path('create/', views.create, name='create'),
    #path('<str:room_name>/', views.room, name='room'),
]