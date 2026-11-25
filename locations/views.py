import pandas as pd
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .cache import get_cached_list, invalidate_list, set_cached_list
from .filters import LocationFilter, LocationOrdering
from .models import Category, Location, Subscription
from .permissions import CategoryPermission, OwnerOrStaff
from .serializers import CategorySerializer, LocationSerializer
from .traffic import record_view

CSV_TEXT_COLUMNS = ("title", "description", "address")
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _escape_csv_formulas(rows):
    sanitized = []
    for row in rows:
        item = dict(row)
        for col in CSV_TEXT_COLUMNS:
            val = item.get(col)
            if isinstance(val, str) and val.lstrip(" ").startswith(CSV_FORMULA_PREFIXES):
                item[col] = f"'{val}"
        sanitized.append(item)
    return sanitized


class CategoryViewSet(ModelViewSet):
    lookup_value_converter = "int"
    queryset = Category.objects.order_by("name", "pk")
    serializer_class = CategorySerializer
    permission_classes = [CategoryPermission]

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({"name": ["category with this name already exists."]})

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({"name": ["category with this name already exists."]})

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({"detail": "Category is in use."}, status=409)


class LocationViewSet(ModelViewSet):
    lookup_value_converter = "int"
    serializer_class = LocationSerializer
    permission_classes = [OwnerOrStaff]
    filter_backends = [DjangoFilterBackend, SearchFilter, LocationOrdering]
    filterset_class = LocationFilter
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "rating", "popularity"]
    ordering = ["-created_at"]

    def get_throttles(self):
        self.throttle_scope = "export" if self.action == "export" else None
        return super().get_throttles()

    def get_queryset(self):
        queryset = Location.objects.active()
        if self.action in ("update", "partial_update", "destroy"):
            return queryset.select_for_update()
        return queryset.with_metrics()

    def filter_queryset(self, queryset):
        if self.action in ("list", "export"):
            return super().filter_queryset(queryset)
        return queryset

    def list(self, request, *args, **kwargs):
        data = get_cached_list(request)
        if data is None:
            data = super().list(request, *args, **kwargs).data
            set_cached_list(request, data, timeout=60)
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        location = self.get_object()
        if request.method == "GET" and record_view(request, location):
            location = get_object_or_404(self.get_queryset(), pk=location.pk)
        return Response(self.get_serializer(location).data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        location = serializer.save(author=request.user)
        invalidate_list()
        fresh = Location.objects.with_metrics().get(pk=location.pk)
        return Response(self.get_serializer(fresh).data, status=201)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        location = self.get_object()
        serializer = self.get_serializer(location, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_list()
        fresh = Location.objects.with_metrics().get(pk=location.pk)
        return Response(self.get_serializer(fresh).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        location = self.get_object()
        location.deleted_at = timezone.now()
        location.save(update_fields=["deleted_at", "updated_at"])
        invalidate_list()
        return Response(status=204)

    @action(detail=False)
    def export(self, request):
        file_format = request.query_params.get("format", "json")
        if file_format not in ("csv", "json"):
            raise ValidationError({"format": "Choose json or csv."})

        queryset = self.filter_queryset(self.get_queryset())
        data = self.get_serializer(queryset, many=True).data
        if file_format == "json":
            return Response(
                data,
                headers={"Content-Disposition": 'attachment; filename="locations.json"'},
            )

        columns = list(self.get_serializer().fields.keys())
        frame = pd.DataFrame.from_records(_escape_csv_formulas(data), columns=columns)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="locations.csv"'
        frame.to_csv(response, index=False)
        return response

    @action(detail=True, methods=["put", "delete"], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def subscription(self, request, pk=None):
        location = get_object_or_404(Location.objects.active().select_for_update(), pk=pk)
        if request.method == "PUT":
            Subscription.objects.get_or_create(location=location, user=request.user)
        else:
            Subscription.objects.filter(location=location, user=request.user).delete()
        return Response(status=204)
