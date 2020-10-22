from django.db import models
from django.contrib.auth.models import AbstractUser, Permission

class Game(models.Model):
    @staticmethod
    def join(player, game_name):
        illus_perm = Permission.objects.get(codename="illustrate_player")
        guess_perm = Permission.objects.get(codename="guess_player")       
        
        game, created = Game.objects.get_or_create(name=game_name)
        player.game = game
        
        if created:
            player.user_permissions.add(illus_perm)
        else:
            player.user_permissions.add(guess_perm)
        player.save() 
        print(f"THIS IS THE PLAYER {player.username}'S PERMISSIONS {player.user_permissions.all()}")
        

    @staticmethod
    def update_turn(game_name):
        """
        Called after every turn's ended. Also when players disconnect.
        """
        game = Game.objects.get(name=game_name)
        players = game.player_set.all()
        
        illus_perm = Permission.objects.get(codename="illustrate_player")
        guess_perm = Permission.objects.get(codename="guess_player")

        # get the current illus index then hand the game
        # to the next player
        illus_index = -1
        for i in range(len(players)):
            if players[i].user_permissions.all()[0] == illus_perm:
                illus_index = i
        if illus_index == -1 and len(players) > 0:
            raise ValueError("A player was deleted before changing turns")
        next_illus_index = illus_index + 1
        
        # last player; end the game flag
        if next_illus_index >= len(players):
            players[len(players)-1].user_permissions.remove(illus_perm)
            players[len(players)-1].user_permissions.add(guess_perm)

            players[0].user_permissions.add(illus_perm)
            players[0].user_permissions.remove(guess_perm)
            return False
    
        game.word = None
        game.illustration = None
        game.save()
        
        players[illus_index].user_permissions.remove(illus_perm)
        players[illus_index].user_permissions.add(guess_perm)

        players[next_illus_index].user_permissions.add(illus_perm)
        players[next_illus_index].user_permissions.remove(guess_perm)
        
        # Turn changed normally
        return True

    @staticmethod
    def update_disconnected(game_name, player_name):
        """
        Deletes the player from database. 
        If player was last one in game, game is deleted.
        """
        game = Game.objects.get(name=game_name)
        player = Player.objects.get(username=player_name)

        if game.player_set.all().count() == 1:
            game.delete()
            return
        
        # will update the turn only if player in illus
        #if player.user_permissions.all()[0].codename == 'illustrate_player':
        #    Game.update_turn(game_name)
            

        player.delete()
        return
    @staticmethod
    def validate_chat_message(chat_object):
        player = Player.objects.get(username=chat_object.player.username)
        game = player.game
        chat_text = chat_object.text
        print(f"{player.username}, {player.user_permissions.all()[0]}")
        if player.user_permissions.all()[0].codename == 'guess_player':
            if chat_text == game.word and not player.guessed:
                player.score += 1
                player.guessed = True
                player.save()
                chat_object.hidden = 1
                chat_object.save()


    name = models.CharField(max_length=10)
    state = models.IntegerField(default=0)
    chat = models.CharField(max_length=100000)
    word = models.CharField(max_length=100, null=True, default=None)
    illustration = models.CharField(max_length=250, null=True, default=None)
    timer = models.IntegerField(default=0)

    def __str__(self):
        return self.name

class Player(AbstractUser):
    class Meta:
        managed = False

        default_permissions = ()

        permissions = (
            ('illustrate_player', 'Player Can Illustrate'),
            ('guess_player', 'Player Can Guess')
        )

    score = models.IntegerField(default=0)
    guessed = models.BooleanField(default=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, null=True, default=None)

    def __str__(self):
        return self.username

class Chat(models.Model):
    @staticmethod
    def get_chat():
        full_chat = [{'player': msg.player.username, 'message': [msg.text, msg.hidden]} for msg in Chat.objects.all()]
        return full_chat

    text = models.CharField(max_length=200)
    hidden = models.IntegerField(default=0)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, default=None)
