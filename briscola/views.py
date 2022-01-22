import json

import zmq
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

# Create your views here.


@login_required
def create(request):
    reply = "you're logged in"
    return HttpResponse(reply)
