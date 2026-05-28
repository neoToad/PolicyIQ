from django.contrib import admin
from django.urls import include, path

from documents.views import DocumentDeleteView, HistoryPageView, UploadPageView
from queries.views import AskPageView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/documents/', include('documents.urls')),
    path('api/queries/', include('queries.urls')),
    path('upload/', UploadPageView.as_view(), name='upload-page'),
    path('history/', HistoryPageView.as_view(), name='history-page'),
    path('documents/<uuid:pk>/delete/', DocumentDeleteView.as_view(), name='document-delete'),
    path('ask/', AskPageView.as_view(), name='ask-page'),
]
