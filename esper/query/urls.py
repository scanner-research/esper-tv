from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/videos', views.videos, name='videos'),
    url(r'^api/frame_and_faces', views.frame_and_faces, name='frames_and_faces'),
    url(r'^api/identities', views.identities, name='identities'),
    url(r'^api/handlabeled', views.handlabeled, name='handlabeled'),
    url(r'^api/search$', views.search, name='search'),
    url(r'^api/search2', views.search2, name='search2'),
    url(r'^api/schema', views.schema, name='schema'),
    url(r'^api/build_index', views.build_index, name='build_index'),
    url(r'^fallback', views.fallback, name='fallback'),
    url(r'^batch_fallback', views.batch_fallback, name='batch_fallback'),
    url(r'^', views.index, name='index')
]
