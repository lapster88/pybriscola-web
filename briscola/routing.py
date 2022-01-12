
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/game/(?P<game_id>\w+)/$', consumers.BriscolaClientConsumer.as_asgi()),
    re_path(r'ws/gameserver/(?P<game_id>\w+)/$', consumers.BriscolaServerConsumer.as_asgi()),
    re_path(r'ws/gameservice/', consumers.BriscolaServiceConsumer.as_asgi()),
]