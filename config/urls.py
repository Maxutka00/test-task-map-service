from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from locations.views import CategoryViewSet, LocationViewSet
from reviews.views import LocationReviews, ReviewDetail, vote

router = SimpleRouter(use_regex_path=False)
router.register("categories", CategoryViewSet, basename="category")
router.register("locations", LocationViewSet, basename="location")


def bad_request_view(request, exception=None):
    return JsonResponse({"detail": "Bad request."}, status=400)


def permission_denied_view(request, exception=None):
    return JsonResponse({"detail": "Permission denied."}, status=403)


def not_found_view(request, exception=None):
    return JsonResponse({"detail": "Not found."}, status=404)


def server_error_view(request):
    return JsonResponse({"detail": "Internal server error."}, status=500)


handler400 = bad_request_view
handler403 = permission_denied_view
handler404 = not_found_view
handler500 = server_error_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/locations/<int:location_id>/reviews/", LocationReviews.as_view()),
    path("api/reviews/<int:pk>/", ReviewDetail.as_view()),
    path("api/reviews/<int:pk>/vote/", vote),
    path("api/", include(router.urls)),
]
