from rest_framework.permissions import SAFE_METHODS, BasePermission


class CategoryPermission(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.is_staff


class OwnerOrStaff(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or request.user.is_staff or obj.author_id == request.user.pk
