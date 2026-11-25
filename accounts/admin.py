from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import OutgoingMail, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "username", "email", "is_staff", "is_active", "date_joined")
    search_fields = ("username", "email")


@admin.register(OutgoingMail)
class OutgoingMailAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "subject", "attempts", "available_at", "sent_at", "created_at")
    list_filter = ("sent_at",)
    search_fields = ("recipient", "subject")
    readonly_fields = ("created_at", "sent_at")
