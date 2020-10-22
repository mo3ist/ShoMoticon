from django.shortcuts import redirect
from django.http import HttpResponse
from .models import Game

def player_has_access(function):
    def wrapper(request, game_name, *args, **kwargs):
        player = request.user
        try:
            game = Game.objects.get(name=game_name)

            if player in game.player_set.all():
                return function(request, game_name, *args, **kwargs)
            else:
                # TODO: make template for this or smthn
                return redirect('index')
        except:
            return redirect('index')

    return wrapper