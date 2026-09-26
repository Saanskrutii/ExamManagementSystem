from django.contrib.auth.models import AbstractUser
from django.db import models
from django_mongodb_backend.fields import ObjectIdAutoField


class CustomUser(AbstractUser):
    id = ObjectIdAutoField(primary_key=True)

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"

    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )

    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
    )

    profile_picture = models.ImageField(
        upload_to="profile_pics/",
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"{self.username} ({self.role})"