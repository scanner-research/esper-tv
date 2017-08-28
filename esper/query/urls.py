from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/videos', views.videos, name='videos'),
    url(r'^api/frame_and_faces', views.frame_and_faces, name='frames_and_faces'),
    url(r'^api/identities', views.identities, name='identities'),
    url(r'^api/handlabeled', views.handlabeled, name='handlabeled'),
    url(r'^api/search', views.search, name='search'),
    url(r'^fallback', views.fallback, name='fallback'),
    url(r'^', views.index, name='index')
]
