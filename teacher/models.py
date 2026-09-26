from django.db import models
from django_mongodb_backend.fields import ObjectIdAutoField
from authentication.models import CustomUser


class Subject(models.Model):
    """
    Subject Model for Exam Management System.
    Stores subjects (e.g., Mathematics, Python Programming) created by Teachers.
    """

    id = ObjectIdAutoField(primary_key=True)

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, null=True)

    # Foreign key relationship linking Subject to CustomUser (Teacher/Admin)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="subjects",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Syllabus(models.Model):
    """
    Syllabus Unit model for a Subject.
    Stores units/modules for subjects (e.g. Unit 1: Introduction to Data Structures).
    """

    id = ObjectIdAutoField(primary_key=True)

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="units",
    )

    unit_number = models.PositiveIntegerField(help_text="Unit number, e.g. 1, 2, 3")
    title = models.CharField(max_length=200, help_text="Unit title, e.g. Intro to Trees")
    description = models.TextField(blank=True, null=True, help_text="Topics covered in this unit")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["unit_number"]
        unique_together = ("subject", "unit_number")

    def __str__(self):
        return f"{self.subject.code} - Unit {self.unit_number}: {self.title}"


class Question(models.Model):
    """
    Question Bank Model for Exam Management System.
    Stores MCQs, True/False, and Descriptive questions linked to Subjects & Syllabus Units.
    """

    id = ObjectIdAutoField(primary_key=True)

    class QuestionType(models.TextChoices):
        MCQ = "MCQ", "Multiple Choice (MCQ)"
        TRUE_FALSE = "TRUE_FALSE", "True / False"
        DESCRIPTIVE = "DESCRIPTIVE", "Descriptive / Short Answer"

    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    unit = models.ForeignKey(
        Syllabus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )

    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.MCQ,
    )
    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
    )
    marks = models.PositiveIntegerField(default=1)

    question_text = models.TextField()

    # Options for MCQ / True-False
    option_a = models.CharField(max_length=255, blank=True, null=True)
    option_b = models.CharField(max_length=255, blank=True, null=True)
    option_c = models.CharField(max_length=255, blank=True, null=True)
    option_d = models.CharField(max_length=255, blank=True, null=True)
    correct_answer = models.CharField(
        max_length=255,
        help_text="Correct option letter (e.g. A, B, C, D or True/False text)",
    )

    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.question_type}] {self.question_text[:50]}..."
