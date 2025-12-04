from django.urls import path, re_path

from . import views, consumers

urlpatterns = [
    path('create/', views.create, name='create'),
    path('observer-token/<str:game_id>/', views.observer_token, name='observer_token'),

    #path('<str:room_name>/', views.room, name='room'),
]
