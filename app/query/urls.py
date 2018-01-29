from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/search2', views.search2, name='search2'),
    url(r'^api/schema', views.schema, name='schema'),
    url(r'^api/subtitles', views.subtitles, name='subtitles'),
    url(r'^api/labeled', views.labeled, name='labeled'),
    url(r'^', views.index, name='index')
]
