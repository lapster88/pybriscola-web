import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer


service_group_name = 'briscola_service'

class BriscolaClientConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.game_id_name = None
        self.game_id = None

    def connect(self):
        print(self.scope['user'])

        # if self.scope['user'].is_authenticated:
        self.accept()
        # else:
        #     self.close()

    def disconnect(self, code):
        pass

    def receive(self, text_data=None, bytes_data=None):
        message = json.loads(text_data)
        message_type = message['message_type']
        print(message_type)
        if message_type == 'create':
            async_to_sync(self.channel_layer.group_send)(
                service_group_name,
                {
                    'type' : 'service.create',
                    'requestor' : self.channel_name,
                    'message' : text_data
                }
            )

        else:
            async_to_sync(self.channel_layer.group_send)(
                self.game_server_id_name,
                {
                    'type': 'player.action',
                    'message': text_data
                }
             )

    def game_update(self, event):
        message = json.loads(event['message'])
        if message['message_type'] == 'create':
            if message['result'] == 'success':
                self.join_game(message['game_id'])
            else:
                self.send('create failed')

        self.send(text_data=event['message'])

    def join_game(self, game_id):
        self.game_id = game_id
        async_to_sync(self.channel_layer.group_add)(self.game_id,
                                                    self.channel_name)


        print('joining game %s' % game_id)



class BriscolaServiceConsumer(WebsocketConsumer):
    groups = [service_group_name]

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.create_requestors = []

    def connect(self):

        self.accept()

    def disconnect(self, code):
        pass

    def receive(self, text_data=None, bytes_data=None):
        message = json.loads(text_data)
        if message['message_type'] == 'create':
            channel_name = self.create_requestors[0]
            self.create_requestors.remove(channel_name)
            async_to_sync(self.channel_layer.send)(
                channel_name,
                {
                    'type': 'game.update',
                    'message': text_data
                }
            )
        pass

    def service_create(self, event):
        message = json.loads(event['message'])
        self.create_requestors.append(event['requestor'])
        self.send(text_data=event['message'])

class BriscolaServerConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.game_id = None

    def connect(self):
        self.accept()


    def disconnect(self, code):
        pass

    def receive(self, text_data=None, bytes_data=None):
        message = json.loads(text_data)
        if message['message_type'] == 'created':
            self.game_id = message['game_id']

            async_to_sync(self.channel_layer.group_send)(
                self.game_id,
                {
                    'type': 'game.update',
                    'message': text_data
                }
            )

    def player_action(self, event):
        self.send(event['message'])
