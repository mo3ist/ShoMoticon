from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import Permission

import json
import pickle

from .models import Game, Player
### SO; when i was sketching the desgin for this god foresaken game i was on mashroums
### I don't know why but I implemented all things in one websocket and 
### complicated stuff a lot (sending and receiving status code, keeping track of them, keeping track of different but equally useless stuff...)

# TODO: make a better self.data

# IMPORTANT: one crusial thing to understand here is how django channels & channel layers
# work. A channel's job is to send and receive messages from ITS OWN UNIQUE client.
# If you want to broadcast a message you can't just send it to other channels directly;
# you'll have to communicate with a middle man (channel layer) which in return is
# responsible for communicating with other channels
# SO: A channel can have 2 things communicating with it: a layer and a unique client

class MainConsumer(WebsocketConsumer):
    # TODO: Explain the status codes and server client communication in this class.
    def connect(self):
        # async_to_sync(self.channel_layer.group_add)(self.)
        self.game_name = self.scope['url_route']['kwargs']['game_name']
        self.player = self.scope['user']
    
        # chosen word
        self.word = None
        # status code given by client
        self.client_status = -1

        async_to_sync(self.channel_layer.group_add)(self.game_name, self.channel_name)
        self.accept()

        # send the status code 0 ==> initial message on connect
        self.data = {
            'status': 0,
            'perm': self.player.user_permissions.all()[0].codename,
            'message': '',
            'player': self.player.username
        } 

        # the variables here are 'data', 'request', 'player'
        # a better way to do this is with a class
        self.channel_layer_data = {
            'type': self.get_send_function.__name__,
            'data': self.data,
            'request': 'send',   # to keep track of who is what preventing loops [and maybe other stuff later]
            'player': self.player.username  # to further track who sent what # client can't reach it here
        }

        async_to_sync(self.channel_layer.group_send)(self.game_name, self.channel_layer_data)

    def receive(self, text_data):
        """
        Players will echo the status codes sent with the response. 
        A thread will be opened to send status code 3 [game ended]
        """
        # TODO: the client can send status codes back to server, if they we're not
        # right the server will crash. This is the ideal place to handle this, I think.
        
        self.channel_layer_data['data'] = json.loads(text_data)
        self.channel_layer_data['request'] = 'receive'
        async_to_sync(self.channel_layer.group_send)(self.game_name, self.channel_layer_data)
        

    def disconnect(self, close_code):
        # TODO: Players can exit and still be in the database if they didn't
        # exit properly : e.g. server closed
        Game.update_disconnected(self.player)

    def get_send_function(self, event):
        self.data['status'] = event['data']['status']
        self.data['message'] = event['data']['message']
        self.data['player'] = event['data']['player']

        # update to whom sent this
        self.channel_layer_data['player'] = event['player']

        illus_perm = Permission.objects.get(codename="illustrate_player")
        # print([[x.username, x.user_permissions.all()] for x in self.player.game.player_set.all()])
        if self.player.has_perm('game.' + illus_perm.codename):
            return self.illustrator_sender(event)
        return self.guesser_sender(event)
    
    # I HATE that the code in illustrator_sender is almost identical to that of guesser_sender

    def illustrator_sender(self, event):
        if self.data['status'] == 0:
            # player sent joining confirmation:
            # server decides wheather to send status code 1 or not
            # if self.player.game.player_set.all().count() > 1:
            #     self.data['status'] = 1
            #     self.data['message'] = ['word1', 'word2', 'word3']
            #     self.send(text_data=json.dumps(self.data))

            if event['request'] == 'send':
                # if self.client_status < 0:
                    # layer sent this from server, send it to client
                self.send(text_data=json.dumps(self.data))          
                    # self.client_status = 0     

            elif event['request'] == 'receive':
                # This condition is True in whenever a new player joins
                if self.player.game.player_set.all().count() > 1:
                    # If this condition is True then there's 2 possibilities
                    # 1- self.client_status is still -1 (the game will then start)
                    # 2- self.client_status > 0 (a new player has joined while minimum number of players are playing)

                    if self.client_status < 0:
                        self.data['status'] = 1

                        self.channel_layer_data['data'] = self.data
                        self.channel_layer_data['request'] = 'send'
                        async_to_sync(self.channel_layer.group_send)(self.game_name, self.channel_layer_data)
                        
                        self.client_status = 0

                    elif self.client_status > 0:
                        # a new player has joined, send him the latest status
                        self.data['status'] = self.client_status
                        
                        self.channel_layer_data['data'] = self.data
                        self.channel_layer_data['request'] = 'send'
                        async_to_sync(self.channel_layer.group_send)(self.game_name, self.channel_layer_data)
                        
        elif self.data['status'] == 1:
            # player [illus] sent the chosen word
            # server sends status code 2

            # self.data['status'] = 2
            # self.data['message'] = event['data']['message']

            # self.word = self.data['message']

            # self.send(text_data=json.dumps(self.data))
            if event['request'] == 'send' :
                # self.data['message'] = ''
                if self.client_status < 1:
                    self.data['message'] = ['test', 'word', 'game']  
                    self.send(text_data=json.dumps(self.data)) 
                    self.client_status = 1

            elif event['request'] == 'receive':
                self.data['status'] = 2 # change status
                self.data['message'] = event['data']['message'] # the chosen word gotten from client
                
                # setting the word in [illus] so that [guess]ers can invoke Player.get_word() 
                self.player.word = event['data']['message']
                
                self.channel_layer_data['data'] = self.data
                self.channel_layer_data['request'] = 'send'
                async_to_sync(self.channel_layer.group_send)(self.game_name, self.channel_layer_data)


        elif self.data['status'] == 2:
            # player [illus] sends the illustrations to the server
            # server sends the illustrations to clients [guess] in status code 2
            # player [guess] sends the guesses to the server
            # server checks guesses
            if event['request'] == 'send':
                if self.client_status < 2:
                    self.send(text_data=json.dumps(self.data))
                    self.client_status = 2

            if event['request'] == 'receive':
                self.data['message'] = event['data']['message'] # the things player [illus] is writing in game_screen
                
                # TODO: the condition here is satisfied when either [illus] or [guess] has sent the status code 2
                # so you'll have to figure out a way to filter that
                
                # broadcast to players [guess] AND itself (in the request == send)
                self.channel_layer_data['data'] = self.data
                self.channel_layer_data['request'] = 'send'
                async_to_sync(self.channel_layer.group_send)(self.game_name, self.channel_layer_data)

        elif self.data['status'] == 3:
            # players send confirmation that time is out
            pass

    def guesser_sender(self, event):
        # self.data = event['data']
        if self.data['status'] == 0:
            # player sent joining confirmation:
            # server decides wheather to send status code 1 or not
            if event['request'] == 'send':
                # layer sent this from server, send it to client
                # if self.client_status < 0:
                self.send(text_data=json.dumps(self.data)) 
                    # self.client_status = 0
            else:
                # layer sent this from client, invoke a call to group
                pass 
               

        elif self.data['status'] == 1:
            # player [illus] sent the chosen word
            # server sends status code 2
            # print(self.data)
            # self.data['status'] = 2
            # self.word = self.data['message']
            # self.data['message'] = ''
            # self.send(text_data=json.dumps(self.data))
            
            if event['request'] == 'send':
                # invoked from server, prepare for client the sent it.
                if self.client_status < 1:
                    self.send(text_data=json.dumps(self.data)) 
                    self.client_status = 1

        elif self.data['status'] == 2:
            if event['request'] == 'send':
                # the send came from player [illus]

                if self.client_status < 2:
                    # first [send] request => player [illus] has chosen a word

                    # get the word from [illus] 
                    self.word = Player.get_word()
                    # remeber player [illus]'s self.data is different from player [guess]'s
                    # BUT in get_send_function we assign self.data['message'] = event['data']['message']
                    # so you'll have to delete it
                    self.data['message'] = ''

                    self.send(text_data=json.dumps(self.data))
                    self.client_status = 2
                
                elif self.client_status == 2:
                    # execution here will happen after the first [send] request
                    # from player [illus] => what players [illus is writing]
                    self.send(text_data=json.dumps(self.data))
            
            elif event['request'] == 'receive':
                if self.data['message'] == Player.get_word():
                    self.player.score += 1
                    print([(x.username, x.score) for x in Player.objects.all()])     


        elif self.data['status'] == 3:
            # players send confirmation that time is out
            pass

        elif self.data['status'] == 5:
            Game.update_turn(self.game_name)