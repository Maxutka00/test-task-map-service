from decimal import Decimal

import django_filters
from django import forms
from django.db.models import F
from rest_framework.filters import OrderingFilter

from .models import Location

MAX_BIGINT = 2**63 - 1
FLOAT_EPSILON = Decimal("0.000000001")


class PositiveBigIntFilter(django_filters.Filter):
    field_class = forms.IntegerField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("min_value", 1)
        kwargs.setdefault("max_value", MAX_BIGINT)
        super().__init__(*args, **kwargs)


class LocationFilter(django_filters.FilterSet):
    category = PositiveBigIntFilter(field_name="category_id")
    author = PositiveBigIntFilter(field_name="author_id")
    rating = django_filters.NumberFilter(method="filter_rating")
    min_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="gte")
    max_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="lte")

    class Meta:
        model = Location
        fields = ("category", "author", "rating", "min_rating", "max_rating")

    def filter_rating(self, queryset, name, value):
        center = Decimal(str(float(value)))
        return queryset.filter(
            rating__gte=center - FLOAT_EPSILON,
            rating__lte=center + FLOAT_EPSILON,
        )


class LocationOrdering(OrderingFilter):
    def filter_queryset(self, request, queryset, view):
        fields = self.get_ordering(request, queryset, view) or []
        order = [
            F("rating").desc(nulls_last=True) if field == "-rating" else field
            for field in fields
        ]
        return queryset.order_by(*order, "pk")
