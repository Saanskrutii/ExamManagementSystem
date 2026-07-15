from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="teacher_dashboard"),
    path("subjects/", views.subjects, name="subjects"),
]
