from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
    path("all_exams/", views.student_all_exams, name="student_all_exams"),
    path("answer_sheets/", views.student_answer_sheets, name="student_answer_sheets"),
    path("attempt/<str:attempt_id>/review/", views.student_attempt_review, name="student_attempt_review"),
    path("settings/", views.student_settings, name="student_settings"),
    path("exam/enter/<str:exam_id>/", views.verify_exam_code, name="verify_exam_code"),
    path("exam/take/<str:exam_id>/", views.take_exam, name="take_exam"),
    path("exam/submit/<str:exam_id>/", views.submit_exam, name="submit_exam"),
    path("exam/result/<str:result_id>/", views.exam_result, name="exam_result"),
    path("exam/report_card/<str:result_id>/", views.download_report_card, name="download_report_card"),
    path("analytics/", views.student_analytics, name="student_analytics"),
]
