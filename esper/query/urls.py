from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/videos/', views.videos, name='videos'),
    url(r'^api/faces/(?P<video_id>[0-9]+)?', views.faces, name='faces'),
    url(r'^', views.index, name='index')
]
