from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework import serializers

from .models import Category, Location

MAX_DESCRIPTION_LENGTH = 10000
COORDINATE_QUANT = Decimal("0.000001")


class CoordinateField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        try:
            parsed = Decimal(str(data))
        except (InvalidOperation, TypeError, ValueError):
            self.fail("invalid")
        if not parsed.is_finite():
            self.fail("invalid")
        if abs(parsed) <= Decimal("1000"):
            data = parsed.quantize(COORDINATE_QUANT, rounding=ROUND_HALF_UP)
        return super().to_internal_value(data)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")


class LocationSerializer(serializers.ModelSerializer):
    description = serializers.CharField(max_length=MAX_DESCRIPTION_LENGTH)
    latitude = CoordinateField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = CoordinateField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    rating = serializers.FloatField(read_only=True, allow_null=True)
    review_count = serializers.IntegerField(read_only=True)
    popularity = serializers.FloatField(read_only=True)

    class Meta:
        model = Location
        fields = (
            "id",
            "title",
            "description",
            "category",
            "address",
            "latitude",
            "longitude",
            "author",
            "created_at",
            "updated_at",
            "rating",
            "review_count",
            "popularity",
        )
        read_only_fields = ("author", "created_at", "updated_at")
