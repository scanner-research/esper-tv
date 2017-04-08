from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^videos', views.videos, name='videos'),
    url(r'^faces', views.faces, name='faces')
]
