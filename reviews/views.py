from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from accounts.models import OutgoingMail, User
from locations.cache import invalidate_list
from locations.models import Location
from locations.permissions import OwnerOrStaff

from .models import Review, Vote
from .serializers import ReviewSerializer, VoteSerializer


class LocationReviews(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        location = get_object_or_404(Location.objects.active(), pk=self.kwargs["location_id"])
        return location.reviews.annotate(
            likes=Count("votes", filter=Q(votes__value=Vote.Value.LIKE)),
            dislikes=Count("votes", filter=Q(votes__value=Vote.Value.DISLIKE)),
        ).order_by("-created_at", "-pk")

    @transaction.atomic
    def create(self, request, location_id):
        location = get_object_or_404(Location.objects.active().select_for_update(), pk=location_id)
        if location.reviews.filter(author=request.user).exists():
            return Response({"detail": "You already reviewed this location."}, status=409)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(location=location, author=request.user)

        recipients = (
            User.objects.filter(
                Q(pk=location.author_id) | Q(subscription__location=location),
                is_active=True,
            )
            .exclude(pk=request.user.pk)
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )
        subject = f"New review: {location.title}".replace("\r", " ").replace("\n", " ")
        body = f"{request.user.username} rated {location.title} {review.rating}/5.\n\n{review.comment}"
        OutgoingMail.objects.bulk_create(
            [OutgoingMail(recipient=email, subject=subject, body=body) for email in recipients]
        )

        invalidate_list()
        return Response(serializer.data, status=201)


class ReviewDetail(generics.DestroyAPIView):
    permission_classes = [OwnerOrStaff]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(location__deleted_at__isnull=True).select_for_update(of=("self",))

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_list()

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@api_view(["PUT", "DELETE"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def vote(request, pk):
    review = get_object_or_404(
        Review.objects.select_for_update(of=("self",)).filter(location__deleted_at__isnull=True),
        pk=pk,
    )
    if request.method == "DELETE":
        Vote.objects.filter(review=review, user=request.user).delete()
        return Response(status=204)

    serializer = VoteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    Vote.objects.update_or_create(
        review=review,
        user=request.user,
        defaults=serializer.validated_data,
    )
    return Response(serializer.validated_data)
