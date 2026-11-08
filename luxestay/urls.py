from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]

# Show uploaded room photos while developing, and design preview
if settings.DEBUG:
    from django.views.generic import TemplateView
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # DEBUG-only design preview (clearly commented: remove in Phase 7)
    urlpatterns += [
        path('design-preview/', TemplateView.as_view(template_name='design_preview.html'), name='design_preview'),
    ]