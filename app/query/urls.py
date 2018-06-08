from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/search', views.search, name='search'),
    url(r'^api/schema', views.schema, name='schema'),
    url(r'^api/subtitles', views.subtitles, name='subtitles'),
    url(r'^api/labeled', views.labeled, name='labeled'),
    url(r'^api/newthings', views.newthings, name='newthings'),
    url(r'^', views.index, name='index')
]
