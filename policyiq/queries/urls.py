from django.urls import path

from queries.views import HealthCheckAPIView, QueryAPIView

urlpatterns = [
    path("ask/", QueryAPIView.as_view(), name="query-ask"),
    path("health/", HealthCheckAPIView.as_view(), name="health-check"),
]
