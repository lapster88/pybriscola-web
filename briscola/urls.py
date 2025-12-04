from django.urls import path, re_path

from . import views, consumers

urlpatterns = [
    path('create/', views.create, name='create'),
    path('token/<str:game_id>/', views.issue_token, name='issue_token'),
    path('observer-token/<str:game_id>/', views.observer_token, name='observer_token'),
    path('game/<str:game_id>/delete/', views.delete_game, name='delete_game'),
    path('game/<str:game_id>/sync/', views.sync_game, name='sync_game'),
    path('game/<str:game_id>/status/', views.game_status, name='game_status'),
    path('join/observer/<str:game_id>/', views.join_observer, name='join_observer'),
    path('health/', views.health, name='health'),

    #path('<str:room_name>/', views.room, name='room'),
]
