
import json
import random
from datetime import datetime, timedelta
from bson import ObjectId
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from config.db import (
    subjects_collection,
    exams_collection,
    questions_collection,
    attempts_collection,
    results_collection,
)


def get_dynamic_exam_duration(exam):
    """
    Returns the exam duration in minutes as set by the teacher (defaults to 45 mins).
    """
    try:
        dur = int(exam.get("duration_minutes", 45))
        if dur > 0:
            return dur
    except Exception:
        pass
    return 45


@login_required(login_url="login")
def student_dashboard(request):
    """
    Student Dashboard listing active/upcoming exams and past scorecard summaries.
    """
    if request.user.role != "STUDENT":
        messages.error(request, "Access denied. Student portal only.")
        return redirect("login")

    # Machine clock is UTC; stored start/end times come from browser (IST)
    # Add IST offset (+5:30) to UTC so comparison is apples-to-apples
    now_local = datetime.utcnow() + timedelta(hours=5, minutes=30)

    # 1. Fetch available exams created by teachers
    exams_cursor = exams_collection.find().sort("created_at", -1)
    available_exams = []

    for exam in exams_cursor:
        exam["id"] = str(exam["_id"])
        
        # Attach Subject details via PyMongo
        sub_doc = subjects_collection.find_one({"_id": exam.get("subject_id")})
        if sub_doc:
            exam["subject"] = {
                "name": sub_doc.get("name", ""),
                "code": sub_doc.get("code", "")
            }

        start_str = exam.get("start_time", "")
        end_str = exam.get("end_time", "")
        status = "SCHEDULED"
        exam["duration_minutes"] = get_dynamic_exam_duration(exam)

        if start_str and end_str:
            try:
                dt_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%M")
                dt_end = datetime.strptime(end_str, "%Y-%m-%dT%H:%M")
                if now_local >= dt_start and now_local <= dt_end:
                    status = "LIVE"
                elif now_local > dt_end:
                    status = "COMPLETED"
                else:
                    status = "SCHEDULED"
            except Exception:
                pass
        
        exam["dynamic_status"] = status

        # Count how many times student has attempted this exam (for display)
        attempt_count = attempts_collection.count_documents({
            "student_id": request.user.id,
            "exam_id": exam["_id"],
            "is_submitted": True
        })
        exam["attempt_count"] = attempt_count

        # Show on dashboard for all LIVE exams (students can re-attempt)
        if status == "LIVE":
            available_exams.append(exam)
        elif status == "SCHEDULED":
            available_exams.append(exam)

    # 2. Fetch top 10 past results for this student for dashboard preview
    results_cursor = results_collection.find({"student_id": request.user.id}).sort("evaluated_at", -1).limit(10)
    past_results = []
    
    for r in results_cursor:
        r["id"] = str(r["_id"])
        
        # Attach exam title & subject details via PyMongo
        exam_doc = exams_collection.find_one({"_id": r.get("exam_id")})
        if exam_doc:
            r["exam_title"] = exam_doc.get("title", "Exam")
            sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
            if sub_doc:
                r["subject_name"] = sub_doc.get("name", "")
                r["subject_code"] = sub_doc.get("code", "")
        
        past_results.append(r)

    return render(request, "student_dashboard.html", {
        "available_exams": available_exams,
        "past_results": past_results,
    })


@login_required(login_url="login")
def student_all_exams(request):
    """
    Dedicated view listing all active, upcoming, and past exams for students.
    """
    if request.user.role != "STUDENT":
        messages.error(request, "Access denied. Student portal only.")
        return redirect("login")

    now_local = datetime.utcnow() + timedelta(hours=5, minutes=30)
    exams_cursor = exams_collection.find().sort("created_at", -1)
    all_exams = []

    for exam in exams_cursor:
        exam["id"] = str(exam["_id"])
        sub_doc = subjects_collection.find_one({"_id": exam.get("subject_id")})
        if sub_doc:
            exam["subject"] = {
                "name": sub_doc.get("name", ""),
                "code": sub_doc.get("code", "")
            }

        start_str = exam.get("start_time", "")
        end_str = exam.get("end_time", "")
        status = "SCHEDULED"
        exam["duration_minutes"] = get_dynamic_exam_duration(exam)

        if start_str and end_str:
            try:
                dt_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%M")
                dt_end = datetime.strptime(end_str, "%Y-%m-%dT%H:%M")
                if now_local >= dt_start and now_local <= dt_end:
                    status = "LIVE"
                elif now_local > dt_end:
                    status = "COMPLETED"
                else:
                    status = "SCHEDULED"
            except Exception:
                pass
        
        exam["dynamic_status"] = status
        attempt_count = attempts_collection.count_documents({
            "student_id": request.user.id,
            "exam_id": exam["_id"],
            "is_submitted": True
        })
        exam["attempt_count"] = attempt_count
        all_exams.append(exam)

    return render(request, "student_all_exams.html", {"all_exams": all_exams})


@login_required(login_url="login")
def student_answer_sheets(request):
    """
    Lists all submitted attempts for the student with direct links to review answer sheets.
    """
    if request.user.role != "STUDENT":
        messages.error(request, "Access denied. Student portal only.")
        return redirect("login")

    attempts_cursor = attempts_collection.find(
        {"student_id": request.user.id, "is_submitted": True}
    ).sort("submitted_at", -1)

    attempts_list = []
    for att in attempts_cursor:
        att["id"] = str(att["_id"])
        exam_doc = exams_collection.find_one({"_id": att.get("exam_id")})
        res_doc = results_collection.find_one({"attempt_id": att["_id"]})
        
        if exam_doc:
            att["exam_title"] = exam_doc.get("title", "Exam")
            sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
            if sub_doc:
                att["subject_name"] = sub_doc.get("name", "")
                att["subject_code"] = sub_doc.get("code", "")
        
        if res_doc:
            att["score"] = res_doc.get("score", 0)
            att["total_marks"] = res_doc.get("total_marks", 0)
            att["percentage"] = res_doc.get("percentage", 0)
            att["status"] = res_doc.get("status", "PENDING")

        attempts_list.append(att)

    return render(request, "student_answer_sheets.html", {"attempts": attempts_list})


@login_required(login_url="login")
def student_attempt_review(request, attempt_id):
    """
    Detailed answer sheet review for a specific student attempt.
    """
    try:
        att_obj_id = ObjectId(attempt_id)
    except Exception:
        return redirect("student_answer_sheets")

    # Teachers can view any student attempt; students can only view their own
    query = {"_id": att_obj_id}
    if request.user.role == "STUDENT":
        query["student_id"] = request.user.id

    attempt = attempts_collection.find_one(query)
    if not attempt:
        messages.error(request, "Attempt record not found or access denied.")
        return redirect("student_answer_sheets" if request.user.role == "STUDENT" else "student_submissions")

    exam_doc = exams_collection.find_one({"_id": attempt.get("exam_id")})
    res_doc = results_collection.find_one({"attempt_id": att_obj_id})

    subject_name = "General"
    subject_code = ""
    if exam_doc:
        sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
        if sub_doc:
            subject_name = sub_doc.get("name", "General")
            subject_code = sub_doc.get("code", "")

    # Fetch student user details
    from django.contrib.auth import get_user_model
    User = get_user_model()
    student_user = User.objects.filter(id=attempt.get("student_id")).first()

    responses = attempt.get("responses", {})
    question_times = attempt.get("question_times", {})
    answer_review = []

    if exam_doc:
        for i, qid in enumerate(exam_doc.get("question_ids", []), start=1):
            q_doc = questions_collection.find_one({"_id": qid})
            if not q_doc:
                continue

            q_id_str = str(qid)
            student_ans = responses.get(q_id_str, "")
            correct_ans = q_doc.get("correct_answer", "")
            q_type = q_doc.get("question_type", "MCQ")
            marks = int(q_doc.get("marks", 1))
            time_spent = int(question_times.get(q_id_str, 0))

            if not student_ans:
                outcome = "skipped"
                earned_marks = 0
            elif q_type == "DESCRIPTIVE":
                outcome = "descriptive"
                earned_marks = 0
            elif student_ans.strip().upper() == correct_ans.strip().upper():
                outcome = "correct"
                earned_marks = marks
            else:
                outcome = "wrong"
                earned_marks = 0

            answer_review.append({
                "number": i,
                "question_text": q_doc.get("question_text", ""),
                "question_type": q_type,
                "marks": marks,
                "earned_marks": earned_marks,
                "student_ans": student_ans or "—",
                "correct_ans": correct_ans or "—",
                "outcome": outcome,
                "time_spent": time_spent,
                "option_a": q_doc.get("option_a", ""),
                "option_b": q_doc.get("option_b", ""),
                "option_c": q_doc.get("option_c", ""),
                "option_d": q_doc.get("option_d", ""),
            })

    return render(request, "student_attempt_review.html", {
        "attempt": attempt,
        "result": res_doc,
        "exam": exam_doc,
        "subject_name": subject_name,
        "subject_code": subject_code,
        "student_user": student_user,
        "answer_review": answer_review,
        "correct_count": sum(1 for q in answer_review if q["outcome"] == "correct"),
        "wrong_count": sum(1 for q in answer_review if q["outcome"] == "wrong"),
        "skipped_count": sum(1 for q in answer_review if q["outcome"] == "skipped"),
    })


@login_required(login_url="login")
def student_settings(request):
    """
    Student Settings: Profile Details & Password Change.
    """
    if request.user.role != "STUDENT":
        messages.error(request, "Access denied. Student portal only.")
        return redirect("login")

    user = request.user
    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "update_profile":
            user.first_name = request.POST.get("first_name", "").strip()
            user.last_name = request.POST.get("last_name", "").strip()
            email = request.POST.get("email", "").strip()
            if email:
                user.email = email
            user.phone_number = request.POST.get("phone_number", "").strip()

            if request.FILES.get("profile_picture"):
                user.profile_picture = request.FILES["profile_picture"]

            user.save()
            messages.success(request, "Profile updated successfully!")
            return redirect("student_settings")

        elif action == "change_password":
            current_password = request.POST.get("current_password", "")
            new_password = request.POST.get("new_password", "")
            confirm_password = request.POST.get("confirm_password", "")

            if not user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            elif len(new_password) < 6:
                messages.error(request, "New password must be at least 6 characters long.")
            else:
                user.set_password(new_password)
                user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed successfully!")
                return redirect("student_settings")

    return render(request, "student_settings.html", {"user_obj": user})


@login_required(login_url="login")
def verify_exam_code(request, exam_id):
    """
    Renders/processes access code verification. Once verified,
    starts the student's exam attempt.
    """
    try:
        exam_obj_id = ObjectId(exam_id)
    except Exception:
        return redirect("student_dashboard")

    exam = exams_collection.find_one({"_id": exam_obj_id})
    if not exam:
        return redirect("student_dashboard")

    if request.method == "POST":
        code_input = request.POST.get("access_code", "").strip()
        correct_code = exam.get("access_code", "")

        if code_input == correct_code:
            # Always create a FRESH attempt so students can re-attempt
            # (delete any stale incomplete attempt first to avoid orphans)
            attempts_collection.delete_many({
                "student_id": request.user.id,
                "exam_id": exam_obj_id,
                "is_submitted": False
            })
            attempts_collection.insert_one({
                "student_id": request.user.id,
                "exam_id": exam_obj_id,
                "responses": {},
                "started_at": datetime.utcnow(),
                "is_submitted": False
            })

            return redirect("take_exam", exam_id=exam_id)
        else:
            messages.error(request, "Incorrect Exam Access Code. Please try again.")

    sub_doc = subjects_collection.find_one({"_id": exam.get("subject_id")})
    exam["subject_name"] = sub_doc.get("name", "") if sub_doc else ""
    exam["id"] = str(exam["_id"])

    return render(request, "verify_exam_code.html", {
        "exam": exam,
    })


@login_required(login_url="login")
def take_exam(request, exam_id):
    """
    Timed Exam attempt interface with randomized questions.
    """
    try:
        exam_obj_id = ObjectId(exam_id)
    except Exception:
        return redirect("student_dashboard")

    exam = exams_collection.find_one({"_id": exam_obj_id})
    attempt = attempts_collection.find_one({
        "student_id": request.user.id,
        "exam_id": exam_obj_id,
        "is_submitted": False
    })

    if not attempt:
        messages.error(request, "Verification required to start attempt.")
        return redirect("verify_exam_code", exam_id=exam_id)

    # Fetch questions list from database using question_ids stored in exam
    q_ids = exam.get("question_ids", [])
    questions_cursor = questions_collection.find({"_id": {"$in": q_ids}})
    
    questions = []
    for q in questions_cursor:
        q["id"] = str(q["_id"])
        questions.append(q)

    # Randomize questions for student cheating prevention
    random.shuffle(questions)

    # ── Timer: strictly duration_minutes (NOT deadline/end_time) ──────────
    # duration_minutes = how long the student gets once they START the exam
    # end_time = deadline (when the exam ACCESS window closes) — different!
    duration_mins = get_dynamic_exam_duration(exam)
    time_elapsed = (datetime.utcnow() - attempt["started_at"]).total_seconds()
    allowed_secs = int(duration_mins) * 60
    time_remaining_secs = max(0, int(allowed_secs - time_elapsed))

    if time_remaining_secs <= 0:
        # Time expired, auto submit
        return redirect("submit_exam", exam_id=exam_id)

    exam["id"] = str(exam["_id"])

    return render(request, "take_exam.html", {
        "exam": exam,
        "questions": questions,
        "time_remaining_secs": time_remaining_secs,
        "attempt": attempt,
    })


@login_required(login_url="login")
def submit_exam(request, exam_id):
    """
    Auto-grades student attempt responses and saves result document.
    """
    if request.method == "POST":
        try:
            exam_obj_id = ObjectId(exam_id)
        except Exception:
            return redirect("student_dashboard")

        exam = exams_collection.find_one({"_id": exam_obj_id})
        attempt = attempts_collection.find_one({
            "student_id": request.user.id,
            "exam_id": exam_obj_id,
            "is_submitted": False
        })

        if not attempt:
            return redirect("student_dashboard")

        # Gather student responses & question timers from POST
        student_responses = {}
        question_times_raw = request.POST.get("question_times_json", "{}")
        try:
            question_times = json.loads(question_times_raw)
        except Exception:
            question_times = {}

        for qid in exam.get("question_ids", []):
            qid_str = str(qid)
            ans = request.POST.get(f"question_{qid_str}", "").strip()
            student_responses[qid_str] = ans

        # Evaluate responses against correct answers
        score = 0
        total_marks = 0

        for qid in exam.get("question_ids", []):
            q_doc = questions_collection.find_one({"_id": qid})
            if q_doc:
                q_marks = int(q_doc.get("marks", 1))
                total_marks += q_marks

                qid_str = str(qid)
                student_ans = student_responses.get(qid_str, "")
                correct_ans = q_doc.get("correct_answer", "").strip()

                # Case insensitive compare for matching options/text
                if student_ans.lower() == correct_ans.lower():
                    score += q_marks

        percentage = round((score / total_marks * 100), 2) if total_marks > 0 else 0
        passing_marks = int(exam.get("passing_marks", 20))
        status = "PASSED" if score >= passing_marks else "FAILED"

        # Parse anti-cheat violation log submitted with the form
        proctor_violations_raw = request.POST.get("proctor_violations_json", "[]")
        try:
            proctor_violations = json.loads(proctor_violations_raw)
        except Exception:
            proctor_violations = []

        # Update attempt in MongoDB
        attempts_collection.update_one(
            {"_id": attempt["_id"]},
            {"$set": {
                "responses": student_responses,
                "question_times": question_times,
                "proctor_violations": proctor_violations,
                "submitted_at": datetime.utcnow(),
                "is_submitted": True
            }}
        )

        # Graded scorecard logic:
        res_doc = {
            "student_id": request.user.id,
            "exam_id": exam_obj_id,
            "attempt_id": attempt["_id"],
            "score": score,
            "total_marks": total_marks,
            "passing_marks": passing_marks,
            "percentage": percentage,
            "status": status,
            "question_times": question_times,
            "evaluated_at": datetime.utcnow(),
        }
        res_insert = results_collection.insert_one(res_doc)

        messages.success(request, f"Exam submitted successfully! Score: {score}/{total_marks} ({status})")
        return redirect("exam_result", result_id=str(res_insert.inserted_id))

    return redirect("student_dashboard")


@login_required(login_url="login")
def exam_result(request, result_id):
    """
    Renders the student scorecard with full answer-by-answer review.
    """
    try:
        res_obj_id = ObjectId(result_id)
    except Exception:
        return redirect("student_dashboard")

    result = results_collection.find_one({"_id": res_obj_id, "student_id": request.user.id})
    if not result:
        return redirect("student_dashboard")

    result["id"] = str(result["_id"])
    exam_doc = exams_collection.find_one({"_id": result.get("exam_id")})
    if exam_doc:
        result["exam_title"] = exam_doc.get("title", "Exam")
        sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
        if sub_doc:
            result["subject_name"] = sub_doc.get("name", "")
            result["subject_code"] = sub_doc.get("code", "")

    # ── Build per-question review ────────────────────────────────
    answer_review = []
    attempt = attempts_collection.find_one({"_id": result.get("attempt_id")})

    if attempt and exam_doc:
        responses = attempt.get("responses", {})
        for i, qid in enumerate(exam_doc.get("question_ids", []), start=1):
            q_doc = questions_collection.find_one({"_id": qid})
            if not q_doc:
                continue

            q_id_str     = str(qid)
            student_ans  = responses.get(q_id_str, "")
            correct_ans  = q_doc.get("correct_answer", "")
            q_type       = q_doc.get("question_type", "MCQ")
            marks        = int(q_doc.get("marks", 1))

            # Determine outcome
            if not student_ans:
                outcome = "skipped"
            elif q_type == "DESCRIPTIVE":
                outcome = "descriptive"   # can't auto-grade
            elif student_ans.strip().upper() == correct_ans.strip().upper():
                outcome = "correct"
            else:
                outcome = "wrong"

            # Build options map for MCQ display
            options = {}
            if q_type == "MCQ":
                options = {
                    "A": q_doc.get("option_a", ""),
                    "B": q_doc.get("option_b", ""),
                    "C": q_doc.get("option_c", ""),
                    "D": q_doc.get("option_d", ""),
                }
            elif q_type == "TRUE_FALSE":
                options = {"True": "True", "False": "False"}

            answer_review.append({
                "number":       i,
                "question_text": q_doc.get("question_text", ""),
                "question_type": q_type,
                "marks":        marks,
                "student_ans":  student_ans or "—",
                "correct_ans":  correct_ans,
                "outcome":      outcome,
                "options":      options,
            })

    return render(request, "exam_result.html", {
        "result":        result,
        "answer_review": answer_review,
        "correct_count": sum(1 for q in answer_review if q["outcome"] == "correct"),
        "wrong_count":   sum(1 for q in answer_review if q["outcome"] == "wrong"),
        "skipped_count": sum(1 for q in answer_review if q["outcome"] == "skipped"),
    })


@login_required(login_url="login")
def student_analytics(request):
    """
    AI-powered analytics for the student:
    - Score improvement per exam across multiple attempts
    - Weak / Strong topic identification via Gemini AI
    - Study suggestions + YouTube links
    """
    if request.user.role != "STUDENT":
        messages.error(request, "Access denied. Student portal only.")
        return redirect("login")

    from bson import ObjectId
    from teacher.services.ai_service import AIQuestionGeneratorService

    ai_service = AIQuestionGeneratorService()

    # ── 1. Fetch all submitted attempts for this student ─────────
    all_attempts = list(
        attempts_collection.find(
            {"student_id": request.user.id, "is_submitted": True}
        ).sort("submitted_at", 1)
    )

    # ── 2. Group attempts by exam → build improvement timeline ───
    from collections import defaultdict
    exam_attempts_map = defaultdict(list)
    for att in all_attempts:
        exam_id = att.get("exam_id")
        res = results_collection.find_one({"attempt_id": att["_id"]})
        if res:
            exam_attempts_map[str(exam_id)].append({
                "attempt_no": 0,  # filled below
                "score": res.get("score", 0),
                "total_marks": res.get("total_marks", 0),
                "percentage": res.get("percentage", 0),
                "status": res.get("status", ""),
                "submitted_at": att.get("submitted_at"),
            })

    # Build improvement data per exam + Peer Benchmarking
    improvement_data = []
    for exam_id_str, entries in exam_attempts_map.items():
        for idx, e in enumerate(entries):
            e["attempt_no"] = idx + 1
        exam_obj_id = ObjectId(exam_id_str)
        exam_doc = exams_collection.find_one({"_id": exam_obj_id})
        exam_title = exam_doc.get("title", "Exam") if exam_doc else "Exam"
        first_pct = entries[0]["percentage"] if entries else 0
        last_pct  = entries[-1]["percentage"] if entries else 0
        improvement = round(last_pct - first_pct, 1)

        # ── MongoDB $facet Aggregation Pipeline for Peer Benchmarking ──────
        # Instead of fetching all results into Python and processing in-memory,
        # we push the computation down to MongoDB using a $facet pipeline.
        # This runs in O(log n) with the idx_results_exam_score compound index.
        facet_pipeline = [
            {"$match": {"exam_id": exam_obj_id}},
            {
                "$facet": {
                    "stats": [
                        {
                            "$group": {
                                "_id": None,
                                "class_highest": {"$max": "$percentage"},
                                "class_lowest":  {"$min": "$percentage"},
                                "class_avg":     {"$avg": "$percentage"},
                                "total_students": {"$sum": 1},
                            }
                        }
                    ],
                    "sorted_scores": [
                        {"$sort": {"score": -1}},
                        {"$project": {"percentage": 1, "_id": 0}},
                    ],
                }
            },
        ]
        facet_result = list(results_collection.aggregate(facet_pipeline))
        if facet_result and facet_result[0]["stats"]:
            stats = facet_result[0]["stats"][0]
            class_highest = round(stats.get("class_highest", last_pct), 1)
            class_lowest  = round(stats.get("class_lowest",  last_pct), 1)
            class_avg     = round(stats.get("class_avg",     last_pct), 1)
            total_students_attempted = stats.get("total_students", 1)
            # Compute rank from server-sorted scores list
            sorted_scores = [s["percentage"] for s in facet_result[0]["sorted_scores"]]
            student_rank  = next(
                (i + 1 for i, p in enumerate(sorted_scores) if p <= last_pct),
                total_students_attempted,
            )
        else:
            class_highest = last_pct
            class_lowest  = last_pct
            class_avg     = last_pct
            student_rank  = 1
            total_students_attempted = 1


        improvement_data.append({
            "exam_title":   exam_title,
            "attempts":     entries,
            "improvement":  improvement,
            "latest_pct":   last_pct,
            "latest_status": entries[-1]["status"] if entries else "",
            "class_highest": class_highest,
            "class_avg":    class_avg,
            "class_lowest": class_lowest,
            "student_rank": student_rank,
            "total_students_attempted": total_students_attempted,
        })

    # ── 3. Get most recent attempt → analyse wrong/correct Qs + Question Timers ───
    ai_analysis = None
    question_time_analysis = []

    if all_attempts:
        latest_att = all_attempts[-1]
        exam_doc = exams_collection.find_one({"_id": latest_att.get("exam_id")})
        exam_title = exam_doc.get("title", "Exam") if exam_doc else "Exam"

        # Fetch subject name for context
        subject_name = "General"
        if exam_doc:
            sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
            if sub_doc:
                subject_name = sub_doc.get("name", "General")

        # Classify questions as wrong / correct & attach question times
        responses = latest_att.get("responses", {})
        question_times = latest_att.get("question_times", {})
        wrong_questions  = []
        correct_questions = []

        if exam_doc:
            for i, q_id in enumerate(exam_doc.get("question_ids", []), start=1):
                q_id_str = str(q_id)
                q_doc = questions_collection.find_one({"_id": q_id})
                if not q_doc:
                    continue

                student_answer = responses.get(q_id_str, "")
                correct_ans = q_doc.get("correct_answer", "")
                q_type      = q_doc.get("question_type", "MCQ")
                time_secs   = int(question_times.get(q_id_str, 0))

                is_correct = False
                if q_type in ("MCQ", "TRUE_FALSE"):
                    is_correct = str(student_answer).strip().upper() == str(correct_ans).strip().upper()

                if is_correct:
                    correct_questions.append(q_doc)
                else:
                    wrong_questions.append(q_doc)

                question_time_analysis.append({
                    "number": i,
                    "question_text": q_doc.get("question_text", ""),
                    "question_type": q_type,
                    "time_spent": time_secs,
                    "is_correct": is_correct,
                })

        # ── 4. Call Gemini AI ─────────────────────────────────────
        try:
            ai_analysis = ai_service.analyze_student_performance(
                subject_name    = subject_name,
                wrong_questions = wrong_questions,
                correct_questions = correct_questions,
                exam_title      = exam_title,
            )
        except Exception:
            ai_analysis = None

    import json
    chart_exams   = [d["exam_title"] for d in improvement_data]
    chart_scores  = [d["latest_pct"] for d in improvement_data]
    chart_peer_avg = [d["class_avg"] for d in improvement_data]

    return render(request, "student_analytics.html", {
        "improvement_data": improvement_data,
        "ai_analysis":      ai_analysis,
        "question_time_analysis": question_time_analysis,
        "chart_exams_json": json.dumps(chart_exams),
        "chart_scores_json": json.dumps(chart_scores),
        "chart_peer_avg_json": json.dumps(chart_peer_avg),
        "total_attempts":   len(all_attempts),
    })


@login_required(login_url="login")
def download_report_card(request, result_id):
    """
    Generates and returns a downloadable PDF Report Card for the given exam result.
    """
    if request.user.role != "STUDENT":
        messages.error(request, "Access denied.")
        return redirect("login")

    try:
        res_obj_id = ObjectId(result_id)
    except Exception:
        return redirect("student_dashboard")

    result = results_collection.find_one({"_id": res_obj_id, "student_id": request.user.id})
    if not result:
        return redirect("student_dashboard")

    exam_doc = exams_collection.find_one({"_id": result.get("exam_id")})
    exam_title = exam_doc.get("title", "Exam") if exam_doc else "Exam"

    subject_name = "General"
    subject_code = ""
    if exam_doc:
        sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
        if sub_doc:
            subject_name = sub_doc.get("name", "General")
            subject_code = sub_doc.get("code", "")

    # Build question breakdown
    answer_review = []
    attempt = attempts_collection.find_one({"_id": result.get("attempt_id")})

    if attempt and exam_doc:
        responses = attempt.get("responses", {})
        for i, qid in enumerate(exam_doc.get("question_ids", []), start=1):
            q_doc = questions_collection.find_one({"_id": qid})
            if not q_doc:
                continue

            q_id_str     = str(qid)
            student_ans  = responses.get(q_id_str, "")
            correct_ans  = q_doc.get("correct_answer", "")
            q_type       = q_doc.get("question_type", "MCQ")

            if not student_ans:
                outcome = "skipped"
            elif q_type == "DESCRIPTIVE":
                outcome = "descriptive"
            elif student_ans.strip().upper() == correct_ans.strip().upper():
                outcome = "correct"
            else:
                outcome = "wrong"

            answer_review.append({
                "number":        i,
                "question_text": q_doc.get("question_text", ""),
                "question_type": q_type,
                "student_ans":   student_ans or "—",
                "correct_ans":   correct_ans or "—",
                "outcome":       outcome,
            })

    # Prepare report card data
    eval_date = result.get("evaluated_at")
    eval_date_str = eval_date.strftime("%Y-%m-%d %H:%M") if eval_date else "N/A"

    result_data = {
        "id":               str(result["_id"]),
        "exam_title":       exam_title,
        "subject_name":     subject_name,
        "subject_code":     subject_code,
        "evaluated_at_str": eval_date_str,
        "score":            result.get("score", 0),
        "total_marks":      result.get("total_marks", 0),
        "passing_marks":    result.get("passing_marks", 0),
        "percentage":       result.get("percentage", 0),
        "status":           result.get("status", "PENDING"),
        "answer_review":    answer_review,
    }

    student_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
    student_username = request.user.username

    # Generate PDF using ReportLab
    import io
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=18, leading=22,
        textColor=colors.HexColor('#0F172A'), fontName='Helvetica-Bold'
    )
    section_heading = ParagraphStyle(
        'SectionHeading', parent=styles['Heading2'], fontSize=11, leading=15,
        textColor=colors.HexColor('#0F172A'), fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=4
    )
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=8.5, leading=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#1E293B'))
    cell_normal = ParagraphStyle('CellNormal', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor('#334155'))

    story = []

    # 1. Header Banner
    header_data = [
        [
            Paragraph("<b>EXAM MANAGEMENT SYSTEM</b><br/><font size=8.5 color='#64748B'>Official Academic Performance Report Card</font>", title_style),
            Paragraph(f"<font size=8.5 color='#64748B'>Date: {eval_date_str}</font><br/><font size=8 color='#94A3B8'>Doc ID: {str(result['_id'])[:8].upper()}</font>", ParagraphStyle('HeaderRight', alignment=2))
        ]
    ]
    header_table = Table(header_data, colWidths=[360, 180])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0F172A'), spaceBefore=4, spaceAfter=12))

    # 2. Student & Exam Info Grid
    student_info = [
        [Paragraph("<b>Student Details</b>", section_heading), Paragraph("<b>Exam Details</b>", section_heading)],
        [Paragraph(f"<b>Name:</b> {student_name}", cell_normal), Paragraph(f"<b>Exam Title:</b> {exam_title}", cell_normal)],
        [Paragraph(f"<b>Username:</b> {student_username}", cell_normal), Paragraph(f"<b>Subject:</b> {subject_name} ({subject_code})", cell_normal)],
        [Paragraph(f"<b>Student ID:</b> {request.user.id}", cell_normal), Paragraph(f"<b>Passing Marks:</b> {result_data['passing_marks']} / {result_data['total_marks']}", cell_normal)],
    ]
    info_table = Table(student_info, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#F1F5F9')),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    # 3. Score Summary Banner
    status = result_data['status']
    status_bg = colors.HexColor('#DCFCE7') if status == 'PASSED' else colors.HexColor('#FEE2E2')
    status_fg = colors.HexColor('#166534') if status == 'PASSED' else colors.HexColor('#991B1B')
    status_text = "PASSED 🎉" if status == 'PASSED' else "FAILED 🏁"

    score_data = [
        [
            Paragraph("<b>SCORE OBTAINED</b>", ParagraphStyle('ScoreLbl', fontSize=8, textColor=colors.HexColor('#64748B'), fontName='Helvetica-Bold')),
            Paragraph("<b>PERCENTAGE</b>", ParagraphStyle('ScoreLbl', fontSize=8, textColor=colors.HexColor('#64748B'), fontName='Helvetica-Bold')),
            Paragraph("<b>RESULT STATUS</b>", ParagraphStyle('ScoreLbl', fontSize=8, textColor=colors.HexColor('#64748B'), fontName='Helvetica-Bold'))
        ],
        [
            Paragraph(f"<font size=16 color='#0F172A'><b>{result_data['score']} / {result_data['total_marks']}</b></font>", ParagraphStyle('ScoreVal', fontName='Helvetica-Bold')),
            Paragraph(f"<font size=16 color='#0F172A'><b>{result_data['percentage']}%</b></font>", ParagraphStyle('ScoreVal', fontName='Helvetica-Bold')),
            Paragraph(f"<font size=13 color='{status_fg.hexval()}'><b>{status_text}</b></font>", ParagraphStyle('ScoreVal', fontName='Helvetica-Bold'))
        ]
    ]
    score_table = Table(score_data, colWidths=[180, 180, 180])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), status_bg),
        ('BOX', (0,0), (-1,-1), 1.5, status_fg),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 14))

    # 4. Question Breakdown Table
    story.append(Paragraph("Question-by-Question Breakdown", section_heading))
    q_rows = [
        [
            Paragraph("<b>#</b>", cell_bold),
            Paragraph("<b>Question Text</b>", cell_bold),
            Paragraph("<b>Type</b>", cell_bold),
            Paragraph("<b>Your Ans</b>", cell_bold),
            Paragraph("<b>Correct Ans</b>", cell_bold),
            Paragraph("<b>Status</b>", cell_bold)
        ]
    ]

    for q in answer_review[:25]:
        outcome = q.get('outcome', '')
        if outcome == 'correct':
            st_color = colors.HexColor('#166534')
            st_label = 'Correct ✅'
        elif outcome == 'wrong':
            st_color = colors.HexColor('#991B1B')
            st_label = 'Wrong ❌'
        elif outcome == 'skipped':
            st_color = colors.HexColor('#854D0E')
            st_label = 'Skipped ⏭'
        else:
            st_color = colors.HexColor('#6D28D9')
            st_label = 'Descriptive'

        q_rows.append([
            Paragraph(str(q.get('number', '')), cell_normal),
            Paragraph(q.get('question_text', '')[:65] + ('...' if len(q.get('question_text', '')) > 65 else ''), cell_normal),
            Paragraph(q.get('question_type', ''), cell_normal),
            Paragraph(str(q.get('student_ans', '—')), cell_normal),
            Paragraph(str(q.get('correct_ans', '—')), cell_normal),
            Paragraph(f"<b><font color='{st_color.hexval()}'>{st_label}</font></b>", cell_normal)
        ])

    if q_rows:
        q_table = Table(q_rows, colWidths=[24, 230, 60, 70, 80, 76])
        q_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(q_table)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceBefore=4, spaceAfter=8))

    # 5. Footer
    footer_text = Paragraph(
        "<font size=7.5 color='#94A3B8'>This is an official computer-generated exam report card issued by the Exam Management System. No physical signature required.</font>",
        ParagraphStyle('FooterText', alignment=1)
    )
    story.append(footer_text)

    doc.build(story)
    buffer.seek(0)

    clean_filename = "".join(c for c in exam_title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="report_card_{clean_filename}.pdf"'
    return response


