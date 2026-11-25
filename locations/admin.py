from django.contrib import admin

from .models import Category, Location, LocationView, Subscription


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "author", "created_at", "deleted_at")
    list_filter = ("category", "deleted_at")
    search_fields = ("title", "description", "address")


@admin.register(LocationView)
class LocationViewAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "is_guest", "viewed_at")
    list_filter = ("is_guest",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "user")
    search_fields = ("location__title", "user__username", "user__email")
