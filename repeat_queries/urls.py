from django.conf.urls import url

from repeat_queries.views import SQLView

urlpatterns = [
    url(
        r'^request/(?P<request_id>[a-zA-Z0-9\-]+)/sql/$',
        SQLView.as_view(),
        name='request_sql'
    ),
]
