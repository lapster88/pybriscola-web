import datetime
import json
import random
import string

import jwt
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    """Generate a random game id."""
    return ''.join(random.choice(chars) for _ in range(size))


def create(request):
    """
    Create a new game and issue player/observer tokens.
    """
    if request.method not in ['POST', 'GET']:
        return HttpResponseBadRequest('Unsupported method')

    game_id = id_generator()
    exp_minutes = int(request.GET.get('ttl', 60))

    def mint(role, player_id=None):
        payload = {
            'game_id': game_id,
            'role': role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=exp_minutes),
        }
        if player_id is not None:
            payload['player_id'] = player_id
        return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

    players = [
        {'player_id': pid, 'token': mint('player', player_id=pid)}
        for pid in range(5)
    ]
    observer_token_value = mint('observer')
    return JsonResponse({
        'game_id': game_id,
        'players': players,
        'observer_token': observer_token_value,
        'ttl_minutes': exp_minutes,
    })


def observer_token(request, game_id):
    """
    Issue a signed observer token for the given game_id.
    Accepts optional display_name (query param or JSON body).
    """
    if request.method not in ['GET', 'POST']:
        return HttpResponseBadRequest('Unsupported method')

    display_name = request.GET.get('display_name')
    if request.body:
        try:
            body = json.loads(request.body)
            display_name = body.get('display_name', display_name)
        except Exception:
            pass

    exp_minutes = int(request.GET.get('ttl', 60))
    payload = {
        'game_id': game_id,
        'role': 'observer',
        'display_name': display_name,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=exp_minutes)
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return JsonResponse({'token': token, 'ttl_minutes': exp_minutes})
