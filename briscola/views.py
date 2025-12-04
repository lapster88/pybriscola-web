import datetime
import json
import random

import jwt
import redis
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def id_generator(size=6):
    """Generate a random uppercase/digit game id."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(size))


def _mint_token(game_id, role, ttl_minutes, player_id=None, display_name=None):
    payload = {
        'game_id': game_id,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=ttl_minutes),
    }
    if player_id is not None:
        payload['player_id'] = player_id
    if display_name:
        payload['display_name'] = display_name
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def _require_host(request, game_id):
    # Enforce bearer token auth; ignore session cookies to reduce CSRF surface
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    prefix = 'Bearer '
    if not auth_header.startswith(prefix):
        return None, HttpResponseForbidden('Missing host token')
    token = auth_header[len(prefix):]
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None, HttpResponseForbidden('Host token expired')
    except jwt.InvalidTokenError:
        return None, HttpResponseForbidden('Invalid host token')
    if claims.get('role') != 'host' or claims.get('game_id') != game_id:
        return None, HttpResponseForbidden('Host token mismatch')
    return claims, None


def _cors_response(request, response):
    origin = request.META.get("HTTP_ORIGIN")
    allowed = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    if origin and ("*" in allowed or origin in allowed):
        response["Access-Control-Allow-Origin"] = origin
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response["Vary"] = "Origin"
    return response


@csrf_exempt  # API is token-based; we bypass CSRF for non-session use
@require_http_methods(["POST", "GET"])
def create(request):
    if request.method == "OPTIONS":
        return _cors_response(request, JsonResponse({}, status=200))
    """
    Create a new game and issue a host token.
    Host token can later mint player/observer tokens via /briscola/token/<game_id>/.
    """
    game_id = id_generator()
    exp_minutes = int(request.GET.get('ttl', 60))
    host_token = _mint_token(game_id, role='host', ttl_minutes=exp_minutes)
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    client.publish(f"game.{game_id}.control", json.dumps({"command": "create", "game_id": game_id}))
    resp = JsonResponse({
        'game_id': game_id,
        'host_token': host_token,
        'ttl_minutes': exp_minutes,
    })
    return _cors_response(request, resp)


@csrf_exempt  # API is token-based; we bypass CSRF for non-session use
@require_http_methods(["POST"])
def issue_token(request, game_id):
    if request.method == "OPTIONS":
        return _cors_response(request, JsonResponse({}, status=200))
    """
    Issue a player or observer token. Requires Host auth (Bearer host_token).
    Body: JSON { role: "player"|"observer", player_id?, display_name?, ttl_minutes? }
    """
    _, err = _require_host(request, game_id)
    if err:
        return err

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError as e:
        return HttpResponseBadRequest(f'Invalid JSON: {str(e)}')

    role = body.get('role')
    if role not in ('player', 'observer'):
        return HttpResponseBadRequest('Invalid role')
    player_id = body.get('player_id')
    if role == 'player' and player_id is None:
        return HttpResponseBadRequest('player_id required for player token')
    try:
        ttl_minutes = int(body.get('ttl_minutes', 60))
    except (ValueError, TypeError):
        return HttpResponseBadRequest('ttl_minutes must be an integer')
    display_name = body.get('display_name')
    token = _mint_token(
        game_id,
        role=role,
        ttl_minutes=ttl_minutes,
        player_id=player_id,
        display_name=display_name,
    )
    resp = JsonResponse({'token': token, 'ttl_minutes': ttl_minutes})
    return _cors_response(request, resp)


def observer_token(request, game_id):
    """
    Deprecated: retained for compatibility; requires host token in Authorization header.
    """
    if request.method not in ['GET', 'POST']:
        return HttpResponseBadRequest('Unsupported method')

    _, err = _require_host(request, game_id)
    if err:
        return err

    display_name = request.GET.get('display_name')
    if request.body:
        try:
            body = json.loads(request.body)
            display_name = body.get('display_name', display_name)
        except Exception:
            pass

    exp_minutes = int(request.GET.get('ttl', 60))
    token = _mint_token(game_id, role='observer', ttl_minutes=exp_minutes, display_name=display_name)
    return JsonResponse({'token': token, 'ttl_minutes': exp_minutes})


@require_http_methods(["GET"])
def health(request):
    """
    Basic health check: verifies web process is up and can reach Redis.
    """
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return JsonResponse({"status": "ok" if redis_ok else "degraded", "redis": redis_ok})


@require_http_methods(["GET"])
def game_status(request, game_id):
    """
    Lightweight status/metadata for a game_id. For now, returns redis reachability and echoes the id.
    """
    redis_ok = False
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return JsonResponse({
        "game_id": game_id,
        "redis": redis_ok,
        "observers_open": True,
    })


@csrf_exempt  # API is token-based; we bypass CSRF for non-session use
@require_http_methods(["POST"])
def join_observer(request, game_id):
    if request.method == "OPTIONS":
        return _cors_response(request, JsonResponse({}, status=200))
    """
    Client-facing observer join: issues an observer token for a game_id without host auth.
    Suitable for shareable links; no limits on observers per spec.
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        body = {}
    display_name = body.get("display_name")
    try:
        ttl_minutes = int(body.get("ttl_minutes", request.GET.get("ttl", 60)))
    except (ValueError, TypeError):
        ttl_minutes = 60
    token = _mint_token(game_id, role='observer', ttl_minutes=ttl_minutes, display_name=display_name)
    resp = JsonResponse({
        "game_id": game_id,
        "token": token,
        "ttl_minutes": ttl_minutes,
        "role": "observer",
    })
    return _cors_response(request, resp)


@require_http_methods(["POST", "DELETE"])
def delete_game(request, game_id):
    """
    End a game: require host token, clear Redis state/heartbeat keys.
    """
    _, err = _require_host(request, game_id)
    if err:
        return err
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    # signal game service to stop the server
    client.publish(f"game.{game_id}.control", json.dumps({"command": "stop", "game_id": game_id}))
    client.publish(f"game.{game_id}.events", json.dumps({"message_type": "game.ended", "game_id": game_id}))
    return JsonResponse({"status": "deleted", "game_id": game_id})


@require_http_methods(["POST"])
def sync_game(request, game_id):
    """Request a sync snapshot broadcast via control channel (host token required)."""
    _, err = _require_host(request, game_id)
    if err:
        return err
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    client.publish(f"game.{game_id}.control", json.dumps({"command": "sync", "game_id": game_id}))
    return JsonResponse({"status": "sync_requested", "game_id": game_id})
