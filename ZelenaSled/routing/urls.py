from django.urls import path
from . import views

urlpatterns = [
    path('get_walk_paths/', views.get_walk_paths, name='get_walk_paths'),
]