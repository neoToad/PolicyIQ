from django.urls import path

from queries.views import QueryAPIView

urlpatterns = [
    path("ask/", QueryAPIView.as_view(), name="query-ask"),
]
