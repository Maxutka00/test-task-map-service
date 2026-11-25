from rest_framework import serializers

from .models import Review, Vote

MAX_COMMENT_LENGTH = 5000


class ReviewSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=MAX_COMMENT_LENGTH)
    likes = serializers.IntegerField(read_only=True, default=0)
    dislikes = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Review
        fields = ("id", "location", "author", "rating", "comment", "created_at", "likes", "dislikes")
        read_only_fields = ("location", "author", "created_at")


class VoteSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=Vote.Value.choices)
