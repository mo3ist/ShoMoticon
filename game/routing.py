from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/game/<str:game_name>/', consumers.MainConsumer)
]