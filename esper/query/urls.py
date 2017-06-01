from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/videos/', views.videos, name='videos'),
    url(r'^api/faces/', views.faces, name='faces'),
    url(r'^api/identities', views.identities, name='identities'),
    url(r'^', views.index, name='index')
]
