from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

# Create your views here.

def create(request):
    test_data = {'test' : 'data'}
    return JsonResponse(test_data)
