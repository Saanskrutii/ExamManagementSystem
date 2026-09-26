from django.contrib import admin
from .models import Subject, Syllabus, Question


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_by", "created_at")
    search_fields = ("name", "code", "created_by__username")
    list_filter = ("created_at",)
    ordering = ("-created_at",)


@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ("subject", "unit_number", "title", "created_at")
    search_fields = ("title", "subject__name", "subject__code")
    list_filter = ("subject",)
    ordering = ("subject", "unit_number")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("question_text_short", "subject", "unit", "question_type", "difficulty", "marks")
    search_fields = ("question_text", "subject__name", "subject__code")
    list_filter = ("question_type", "difficulty", "subject")
    ordering = ("-created_at",)

    def question_text_short(self, obj):
        return obj.question_text[:60] + "..." if len(obj.question_text) > 60 else obj.question_text
    question_text_short.short_description = "Question Text"
