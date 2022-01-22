
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/client/$', consumers.BriscolaClientConsumer.as_asgi()),
    re_path(r'ws/gameserver/$', consumers.BriscolaServerConsumer.as_asgi()),
    re_path(r'ws/gameservice/', consumers.BriscolaServiceConsumer.as_asgi()),
]