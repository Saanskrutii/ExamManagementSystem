from django.shortcuts import render

# Create your views here.


def dashboard(request):
    return render(request, "teacher_dashboard.html")


def subjects(request):
    return render(request, "subjects.html")