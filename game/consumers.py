from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from .models import Game, Chat, Player

import json
import time
#import multiprocessing ## DOESN'T WORK PROPERLY WITH ASYNC_TO_SYNC
import threading

# NOTE:
# multiprocessing didn't work with async_to_sync, threading did.

# NOTE:
# Player.has_perm('...') doesn't work properly when the permissions are changing constantly.
# Try it in shell and you'll see
# A solution would be: checking for existence in the Player.user_permissions.all()

# NOTE:
# In channels, when you update a one to many model parent like [game] from a child [player],
# the other player instances in the other channels doesn't catch that update.
# I tried in the shell and it works there, it however doesn't work in channels.
# When I updated the game word from illus then tried to see that update from guess, it gave me None though I saved the game model
# But when I queried [game] directly it was successfully updated.
# Player.objects.get(username=self.player.username).game.word THIS WORKED TOO
# NOTE:
# when i tired to save the game like this => Game.objects.get(name=[game]).save(), IT DIDN'T work!!! TF?
# A solution would be: making the functions that use the database more independent, meaning
# To query the name for example to get the model you want instead of taking the old model instance itself as an arg 

class MainConsumer(WebsocketConsumer):
    def connect(self):
        self.game_name = self.scope['url_route']['kwargs']['game_name']
        self.player = self.scope['user']
        self.player_state = 0
        self.player_permission = self.player.user_permissions.all()[0].codename
        
        self.GAME_TIME = 20
        async_to_sync(self.channel_layer.group_add)(self.game_name, self.channel_name)
        
        self.accept()
        
        async_to_sync(self.channel_layer.group_send)(self.game_name, {
            'type': 'handle',
            'state': 0,
            'substate': 0
        })
        

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.game_name,
            self.channel_name
        )

        if self.player_permission == 'illustrate_player':
            print("SENDING SCORE SCREEN")
            async_to_sync(self.channel_layer.group_send)(self.game_name,{
                'type': 'handle',
                'state': 2,
                'substate': 3,
                'change_turn': False
            })
            print("CHANING TURN")
            self.change_turn_logic()
            print("DELETING PLAYER FROM DB")
            Game.update_disconnected(
                self.game_name,
                self.player.username
            )
            # TODO: The timer thread will still be running, track it and kill it  
        
        else:
            Game.update_disconnected(
                self.game_name,
                self.player.username
            )
            async_to_sync(self.channel_layer.group_send)(self.game_name, {
                'type': 'handle',
                'state': 0,
                'substate': 1
            })
            
            async_to_sync(self.channel_layer.group_send)(self.game_name, {
                'type': 'handle',
                'state': 0,
                'substate': 0
            }) 
            
    def receive(self, text_data):
        # TODO: add verfications here
        data = json.loads(text_data)
        
        # some shitty verfs
        try:
            # check for status existance
            status = data['status'] 
            if status == 1:
                word = data['word']
            elif status == 2:
                message = data['message']
            elif status == 3:
                illustration = data['illustration']
        except Exception as e:
            # ban user for sending illegal moves :)
            #raise ValueError(f"Player {self.player} is banned for illegal move.")
            print(e)
            self.disconnect('test')
            return 

        if data['status'] == 1:
            # illustrate_player chose a word

            if self.player_permission == "illustrate_player" and self.player_state > 0:
                self.player.game.timer = self.GAME_TIME
                self.player.game.word = data['word']
                self.player.game.save()
                print(f"TIMER IS : {Game.objects.get(name=self.game_name).timer}")
                data = {
                        'type': 'handle',
                        'state': 2,
                        'substate': 0
                        }
                async_to_sync(self.channel_layer.group_send)(self.game_name, data)
        
        elif data['status'] == 2:

            # I put the logic here because if it was at state 2-1 i'll have to track who sent the message to add it once to Chat and shit.
            # thinking about it after i wrote it, it's easier than what i did here :)
            message = data['message']
            chat_object = Chat.objects.create(text=message, player=self.player)
            Game.validate_chat_message(chat_object)
            all_chat = Chat.get_chat()

            async_to_sync(self.channel_layer.group_send)(self.game_name,{
                'type': 'handle',
                'state': 2,
                'substate': 1,
                'chat': all_chat
                })

        elif data['status'] == 3:
            self.player.game.illustration = data['illustration']
            self.player.game.save()

            data = {
                    'type': 'handle',
                    'state': 2,
                    'substate': 2,
                    'illustration': data['illustration']
                    }

            async_to_sync(self.channel_layer.group_send)(self.game_name, data) 

    def handle(self, event):
        """
        All transmitted messages go through here
        """
        if event['state'] == 0:
            if event['substate'] == 0:
                data = {
                        'state': 0,
                        'perm': self.player_permission,
                        'players': [{'name': p.username, 'perm': p.user_permissions.all()[0].codename} for p in self.player.game.player_set.all()],
                        'chat': Chat.get_chat(),
                        'illustration': Game.objects.get(name=self.game_name).illustration
                        }
                self.send(text_data=json.dumps(data))
                
                if self.player.game.player_set.all().count() > 1:
                    ### OUTRAGOUS PEICE OF SHIT > if self.player.has_perm('game.illustrate_player'): 
                    if self.player_permission == 'illustrate_player':
                        # TODO : This section is a complete mess, this should be where the [update new players] is handled 
                        if not Game.objects.get(name=self.game_name).word: 

                            data = {
                                    'type': 'handle',
                                    'state': 1
                                    }
                        else:
                            data = {
                                    'type': 'handle',
                                    'state': 2,
                                    'substate': 0
                                    }
                        async_to_sync(self.channel_layer.group_send)(self.game_name, data)
                        
            elif event['substate'] == 1:
                # reinitailize variables
                self.player_permission = self.player.user_permissions.all()[0].codename
                self.player_state = 0
                self.player.guessed = False
                self.player.save()

        elif event['state'] == 1:
            if self.player_state < 1:
                self.player_state = 1
                
                if self.player_permission == 'illustrate_player': 
                    data = {
                            'state': 1,
                            'words': ['word1', 'word2', 'word3'],
                            'perm': self.player.user_permissions.all()[0].codename,
                            }
                    self.send(text_data=json.dumps(data))
                else:
                    data = {
                            'state': 1,
                            'perm': self.player.user_permissions.all()[0].codename,
                            }
                    self.send(text_data=json.dumps(data))
        
        elif event['state'] == 2: 
            if event['substate'] == 0 and self.player_state < 2:
                # start game
                if self.player_permission == 'illustrate_player':
                    # This condition is gonna be the first to be fired only once per turn 
                    

                
                    self.score_screen_timer_process = threading.Thread(target=self.score_screen_timer)
                    self.score_screen_timer_process.start()

                # Did it this way because : [READ NOTES]
                timer = Game.objects.get(name=self.game_name).timer

                print(f"{self.player}: {timer}")
                self.player_state = 2
                event = {
                        'data':
                            {
                                'state': 2, 
                                'substate': 0,
                                'perm': self.player.user_permissions.all()[0].codename,
                                'chat': Chat.get_chat(),
                                'illustration': self.player.game.illustration,
                                'timer': timer
                            }    
                        }

                self.send_data(event)
            
            elif event['substate'] == 1:
                # chat

                data = {
                    'state': 2,
                    'substate': 1,
                    'perm': self.player_permission,
                    'chat': event['chat'],
                    'score': [{"player": x.username, "score": x.score} for x in self.player.game.player_set.all()]
                    }
                self.send(text_data=json.dumps(data))


            elif event['substate'] == 2:
                # illustration
                # the data in this state is unique so it should send info to the client not broadcast it
                # other state are unique too
                data = {
                    # type': 'send_data',
                    'data': {
                        'state': 2,
                        'substate': 2,
                        'perm': self.player.user_permissions.all()[0].codename,
                        'illustration': event['illustration']
                        }
                    }
                self.send_data(data)

            elif event['substate'] == 3:
                # score screen 
        
                data = {
                   'state': 2,
                   'substate': 3,
                   'perm': self.player_permission,
                   'scores': [{x.username: x.score} for x in self.player.game.player_set.all()]
                   }

                self.send_data({'data': data}) 
                
                if self.player_permission == 'illustrate_player':
                    # do this once :)
                    change_turn_timer_process = threading.Thread(target=self.change_turn_timer, args=(event['change_turn'],))
                    change_turn_timer_process.start()

            elif event['substate'] == 4:
                # change turn (re-init)
                
                async_to_sync(self.channel_layer.group_send)(self.game_name, {
                    'type': 'handle',
                    'state': 0,
                    'substate': 1
                    })
                async_to_sync(self.channel_layer.group_send)(self.game_name, {
                    'type': 'handle',
                    'state': 0,
                    'substate': 0
                    })


        elif event['state'] == 3: 
            if event['substate'] == 0:
                # gameover screen
                data = {
                        'state': 3,
                        'perm': self.player_permission,
                        'time': 10,
                        'substate': 0,
                        }
                self.send(text_data=json.dumps(data))

                if self.player_permission == 'illustrate_player':
                    data = {
                            'type': 'handle',
                            'state': 3,
                            'substate': 1
                            }
                    gameover_timer_process = threading.Thread(target=self.gameover_timer, args=(data,))
                    gameover_timer_process.start()

            elif event['substate'] == 1:
                # gameover logic
                
                # reset the database fields [not ideal but good enough for a prototype]    
                # reset player model 
                self.player.score = 0
                self.player.save()
                if self.player_permission == 'illustrate_player':
                    # clear game model 
                    self.player.game.word = None
                    self.player.game.illustration = None

                    # drop chat model
                    for msg in Chat.objects.all():
                        msg.delete()
                    
                    data = {
                            'type': 'handle',
                            'state': 0, 
                            'substate': 1
                            }
                    async_to_sync(self.channel_layer.group_send)(self.game_name, data)

                    data = {
                            'type': 'handle',
                            'state': 0,
                            'substate': 0
                            }
                    async_to_sync(self.channel_layer.group_send)(self.game_name, data)
    
    def change_turn_logic(self):
        self.player.game.word = None
        self.player.game.save()

        if self.player_permission == "illustrate_player":
            is_changed = Game.update_turn(self.game_name)
            return is_changed

    def change_turn_timer(self, change_turn):
        time.sleep(5)
        if change_turn: # if it wasn't called long ago in disconnect
            gameover = not self.change_turn_logic()
            print(gameover)
            if gameover:
                data = {
                        'type': 'handle',
                        'state': 3,
                        'substate': 0
                        }
                async_to_sync(self.channel_layer.group_send)(self.game_name, data)
            else:
                self.handle({
                    'state': 2,
                    'substate': 4
                })
        else:
            self.handle({
                'state': 2,
                'substate': 4
                })


    def score_screen_timer(self):
        t = self.GAME_TIME
        while t > 0:
            time.sleep(1)
            t -= 1
            self.player.game.timer = t
            self.player.game.save()

        async_to_sync(self.channel_layer.group_send)(self.game_name, {
            'type': 'handle',
            'state': 2,
            'substate': 3,
            'change_turn': True
            })

    def gameover_timer(self, data):
        # call the gameover logic on all other players 
        time.sleep(10)
        async_to_sync(self.channel_layer.group_send)(self.game_name, data)

    def send_data(self, event):
        self.send(json.dumps(event['data']))

    
