import json
import time
import threading

import jwt
import redis
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.conf import settings


service_group_name = 'briscola_service'
PROTOCOL_VERSION = getattr(settings, 'PROTOCOL_VERSION', '1.0.0')
REDIS_URL = getattr(settings, 'REDIS_URL', 'redis://127.0.0.1:6379/0')
REDIS_PREFIX = 'game'
ACTIVE_CONNECTIONS = {}  # (game_id, player_id) -> channel_name

class BriscolaClientConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_id_name = None
        self.game_id = None
        self.player_id = None
        self.role = None
        self.redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = None
        self.pubsub_thread = None
        self.stop_event = threading.Event()
        # TODO: set game_server_id_name / routing key when a player joins a specific game

    def connect(self):
        print(self.scope['user'])

        # if self.scope['user'].is_authenticated:
        self.accept()
        # else:
        #     self.close()

    def disconnect(self, code):
        self.stop_event.set()
        if self.pubsub:
            try:
                self.pubsub.close()
            except Exception:
                pass
        if self.pubsub_thread and self.pubsub_thread.is_alive():
            self.pubsub_thread.join(timeout=1)
        self.unregister_connection()

    def receive(self, text_data=None, bytes_data=None):
        """Handles all messages coming from the web client. Typically, dispatches messages to the channel layer to
        go to another Consumer for """
        message = json.loads(text_data)
        message_type = message.get('message_type')
        if message_type == 'create':
            async_to_sync(self.channel_layer.group_send)(
                service_group_name,
                {
                    'type' : 'service.create',
                    'requestor' : self.channel_name,
                    'message' : text_data
                }
            )

        elif message_type == 'join':
            self.handle_join(message)

        elif message_type in ['sync', 'bid', 'call-partner-rank', 'call-partner-suit', 'play', 'reorder']:
            if not self.game_id:
                self.send_action_result(message, code='join_failed', reason='Not joined')
                return
            if self.role == 'observer' and message_type != 'sync':
                self.send_action_result(message, code='forbidden', reason='Observers cannot perform actions')
                return
            self.publish_action(message)

        else:
            self.send_action_result(message, code='invalid_action', reason='Unknown message_type')

    def handle_join(self, message):
        token = message.get('token')
        if not token:
            self.send_action_result(message, code='unauthorized', reason='Missing token')
            return
        try:
            claims = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except Exception as exc:  # pylint: disable=broad-except
            self.send_action_result(message, code='unauthorized', reason=f'Invalid token: {exc}')
            return

        game_id = message.get('game_id') or claims.get('game_id')
        if not game_id:
            self.send_action_result(message, code='join_failed', reason='Missing game_id')
            return
        if claims.get('game_id') and claims.get('game_id') != game_id:
            self.send_action_result(message, code='join_failed', reason='Token game_id mismatch')
            return

        role = claims.get('role')
        player_id = claims.get('player_id')
        if role == 'player' and player_id is None:
            self.send_action_result(message, code='join_failed', reason='Missing player_id for player role')
            return
        if role == 'observer':
            player_id = None

        # Handle duplicate connections (new connection wins)
        key = (game_id, player_id)
        prior_channel = ACTIVE_CONNECTIONS.get(key)
        ACTIVE_CONNECTIONS[key] = self.channel_name
        if prior_channel and prior_channel != self.channel_name:
            async_to_sync(self.channel_layer.send)(
                prior_channel,
                {'type': 'force.disconnect'}
            )

        self.game_id = game_id
        self.player_id = player_id
        self.role = role

        self.start_event_listener()
        self.publish_action(message, claims)
        # Immediate ack back to client to satisfy join expectation
        self.send_action_result(message, status='ok')

    def publish_action(self, message, claims=None):
        claims = claims or {}
        envelope = self.build_envelope(message, claims)
        channel = f'{REDIS_PREFIX}.{envelope["game_id"]}.actions'
        self.redis.publish(channel, json.dumps(envelope))

    def build_envelope(self, message, claims=None):
        """Wrap an action with envelope fields expected by game servers."""
        claims = claims or {}
        ts = int(time.time() * 1000)
        payload = dict(message)
        payload.pop('token', None)
        return {
            'message_type': payload.get('message_type'),
            'game_id': payload.get('game_id') or self.game_id or claims.get('game_id'),
            'action_id': payload.get('action_id'),
            'player_id': claims.get('player_id', self.player_id),
            'role': claims.get('role', self.role),
            'ts': ts,
            'version': PROTOCOL_VERSION,
            'origin': 'web',
            'payload': payload
        }

    def send_action_result(self, message, status='error', code=None, reason=None):
        """Send a lightweight action.result directly to the client."""
        action_id = message.get('action_id')
        payload = {
            'message_type': 'action.result',
            'action_id': action_id,
            'status': status,
            'game_id': self.game_id or message.get('game_id'),
        }
        if status == 'error':
            payload['code'] = code
            payload['reason'] = reason
        self.send(text_data=json.dumps(payload))

    def start_event_listener(self):
        if self.pubsub_thread and self.pubsub_thread.is_alive():
            return
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(f'{REDIS_PREFIX}.{self.game_id}.events')

        def _listen():
            while not self.stop_event.is_set():
                for msg in self.pubsub.listen():
                    if self.stop_event.is_set():
                        break
                    if msg.get('type') != 'message':
                        continue
                    data = msg.get('data')
                    try:
                        if isinstance(data, bytes):
                            data = data.decode()
                        event = json.loads(data)
                    except Exception:  # pylint: disable=broad-except
                        continue
                    async_to_sync(self.channel_layer.send)(
                        self.channel_name,
                        {
                            'type': 'redis.event',
                            'event': event
                        }
                    )
                time.sleep(0.01)

        self.pubsub_thread = threading.Thread(target=_listen, daemon=True)
        self.pubsub_thread.start()

    def redis_event(self, event):
        """Invoked via channel_layer from pubsub thread."""
        self.send(text_data=json.dumps(event['event']))

    def force_disconnect(self, event):
        """Called when another connection for the same player takes over."""
        self.send(text_data=json.dumps({
            'message_type': 'action.result',
            'status': 'error',
            'code': 'duplicate_connection_handled',
            'reason': 'Another connection took over'
        }))
        self.close()

    def unregister_connection(self):
        if self.game_id is None:
            return
        key = (self.game_id, self.player_id)
        if ACTIVE_CONNECTIONS.get(key) == self.channel_name:
            del ACTIVE_CONNECTIONS[key]

class BriscolaServiceConsumer(WebsocketConsumer):
    groups = [service_group_name]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        # TODO: issue and return player/observer tokens for the new game_id
