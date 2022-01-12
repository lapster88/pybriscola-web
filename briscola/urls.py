from django.urls import path, re_path

from . import views, consumers

urlpatterns = [
    path('create/', views.create, name='create'),

    #path('<str:room_name>/', views.room, name='room'),
]