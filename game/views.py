from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import Permission
from .models import Player, Game
from .decorators import * 


def index(request):
	if request.method == "POST":
		# create player
		player_name = request.POST.get('player_name')
		game_name = request.POST.get('game_name')
		player = Player(username=player_name)
		player.set_unusable_password()
		player.save()
		login(request, player)
		
		Game.join(player, game_name)
				
		return redirect('game', game_name=game_name)
	
	return render(request, "game/index.html")

@player_has_access
def game(request, game_name):
	context = {'game_name': game_name}
	return render(request, "game/game.html", context)
