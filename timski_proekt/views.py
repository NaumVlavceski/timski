

# Create your views here.
import json
from django.shortcuts import render

def index(request):
    prasalnici = [2,4,6,8,10,12,14,16,18,20,22,27,33,42,54]
    return render(request, "index.html",{"prasalnici": prasalnici})

def prasalnici(request,mesec):

    with open(f'timski_proekt/Prasalnici/{mesec}meseci.json', encoding="utf-8") as f:
        data = json.load(f)
    return render(request, "prasalnici.html", {"quiz": data})