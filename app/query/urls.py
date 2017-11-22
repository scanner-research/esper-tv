from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^api/search2', views.search2, name='search2'),
    url(r'^api/schema', views.schema, name='schema'),
    url(r'^fallback', views.fallback, name='fallback'),
    url(r'^batch_fallback', views.batch_fallback, name='batch_fallback'),
    url(r'^', views.index, name='index')
]
