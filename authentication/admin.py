from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Admin configuration for CustomUser.

    We extend Django's built-in UserAdmin (not plain ModelAdmin) because:
    - It handles password hashing correctly (plain ModelAdmin would store raw passwords)
    - It provides proper user creation/change forms
    - It includes permission management UI out of the box

    We only ADD our custom fields (role, phone_number) to the existing layout.
    """

    # What columns appear in the user list page
    list_display = ("username", "email", "role", "is_staff", "is_active")

    # Clickable filters in the right sidebar
    list_filter = ("role", "is_staff", "is_active")

    # Fields you can search by
    search_fields = ("username", "email", "phone_number")

    # Default ordering
    ordering = ("username",)

    # Fields shown on the user EDIT page
    # We add our custom fields as a new section called "Custom Fields"
    fieldsets = UserAdmin.fieldsets + (
        ("Custom Fields", {
            "fields": ("role", "phone_number"),
        }),
    )

    # Fields shown on the user CREATION page (when adding a new user)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Custom Fields", {
            "fields": ("email", "role", "phone_number"),
        }),
    )
