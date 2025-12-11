

# Create your views here.
import json
from django.shortcuts import render

def index(request):
    with open("timski_proekt/Prasalnici/20meseci.json", encoding="utf-8") as f:

        data = json.load(f)

    return render(request, "index.html", {"quiz": data})