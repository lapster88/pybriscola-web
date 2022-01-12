import json

import zmq
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

# Create your views here.
context = zmq.Context.instance()
game_server_socket = context.socket(zmq.REQ)
#game_server_socket.setsockopt_string(zmq.IDENTITY, '1234')
game_server_socket.connect('tcp://127.0.0.1:5555')

@login_required
def create(request):
    game_server_socket = context.socket(zmq.REQ)
    game_server_socket.setsockopt_string(zmq.IDENTITY, request.user.username)
    game_server_socket.connect('tcp://127.0.0.1:5555')
    print(request.user.username)
    create_game_request = {
        'type' : 'create'
    }
    game_server_socket.send_json(create_game_request)
    reply = game_server_socket.recv()
    # game_server_socket.disconnect()
    # game_server_socket.close()
    return HttpResponse(reply)
