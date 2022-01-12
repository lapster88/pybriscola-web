from channels.generic.websocket import WebsocketConsumer
from zmq import Context, REQ

context = Context.instance()
game_server_router = context.socket(REQ)
game_server_router.connect('tcp://127.0.0.1:5555')

class BriscolaClientConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

    def disconnect(self, code):
        pass

    def receive(self, text_data=None, bytes_data=None):
        pass

class BriscolaServiceConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        self.send('hello')

    def disconnect(self, code):
        pass

    def receive(self, text_data=None, bytes_data=None):
        print(text_data)
        self.send('pong')
        pass

class BriscolaServerConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()


    def disconnect(self, code):
        pass

    def receive(self, text_data=None, bytes_data=None):
        pass