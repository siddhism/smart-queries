from django.conf.urls import url
from blog.views import PostListView

urlpatterns = [
    url('^$', PostListView.as_view(), name='post-list'),
]
