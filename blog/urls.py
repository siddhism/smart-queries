from django.conf.urls import url
from blog.views import PostListView, post_list

urlpatterns = [
    # url('^$', PostListView.as_view(), name='post-list'),
    url('^$', post_list, name='post-list'),
]
