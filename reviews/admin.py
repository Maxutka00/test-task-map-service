from django.contrib import admin

from .models import Review, Vote


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "author", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("comment", "location__title", "author__username")


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("id", "review", "user", "value")
    list_filter = ("value",)
