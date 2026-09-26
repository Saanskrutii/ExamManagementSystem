from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="teacher_dashboard"),

    # Subject URLs
    path("subjects/", views.subjects, name="subjects"),
    path("subjects/join/", views.join_subject, name="join_subject"),
    path("subjects/edit/<str:subject_id>/", views.edit_subject, name="edit_subject"),
    path("subjects/delete/<str:subject_id>/", views.delete_subject, name="delete_subject"),

    # Syllabus URLs
    path("syllabus/", views.syllabus, name="syllabus"),
    path("syllabus/edit/<str:unit_id>/", views.edit_syllabus, name="edit_syllabus"),
    path("syllabus/delete/<str:unit_id>/", views.delete_syllabus, name="delete_syllabus"),
    path("syllabus/upload_pdf/", views.upload_syllabus_pdf, name="upload_syllabus_pdf"),

    # Question Bank URLs
    path("question_bank/", views.question_bank, name="question_bank"),
    path("question_bank/add/", views.add_question, name="add_question"),
    path("question_bank/edit/<str:question_id>/", views.edit_question, name="edit_question"),
    path("question_bank/delete/<str:question_id>/", views.delete_question, name="delete_question"),

    # AI Question Generator URLs
    path("ai_question_generator/", views.ai_question_generator, name="ai_question_generator"),
    path("ai_question_generator/save/", views.save_generated_questions, name="save_generated_questions"),

    # Exam Creation & Scheduling URLs
    path("create_test/", views.create_test, name="create_test"),
    path("scheduled_exams/", views.scheduled_exams, name="scheduled_exams"),
    path("delete_exam/<str:exam_id>/", views.delete_exam, name="delete_exam"),

    # Feature URLs
    path("student_submissions/", views.student_submissions, name="student_submissions"),
    path("submission/<str:attempt_id>/review/", views.teacher_submission_review, name="teacher_submission_review"),
    path("results/", views.results, name="results"),
    path("results/export_csv/", views.export_results_csv, name="export_results_csv"),
    path("analytics/", views.analytics, name="analytics"),
    path("students/", views.students, name="students"),
    path("settings/", views.settings, name="settings"),

    # Exam Edit URL
    path("exam/edit/<str:exam_id>/", views.edit_exam, name="edit_exam"),
]
