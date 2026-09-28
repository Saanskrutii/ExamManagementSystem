import json
from datetime import datetime
from bson import ObjectId
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash

from config.db import (
    subjects_collection,
    syllabus_collection,
    questions_collection,
    exams_collection,
    attempts_collection,
    results_collection,
)
from .utils import extract_syllabus_from_pdf
from .validators import validate_teacher_subject_access, validate_teacher_unit_access, sanitize_input_string, get_user_id_variants
from .decorators import require_teacher_subject_access, require_subject_access
from .services.ai_service import AIQuestionGeneratorService


def is_admin_or_superuser(user):
    return user.role == "ADMIN" or user.is_superuser


def get_teacher_subjects_query(user):
    """
    Returns PyMongo query filter for subjects accessible by the given teacher (owned OR co-taught).
    Uses get_user_id_variants to support BSON ObjectId, string, and integer user IDs seamlessly.
    """
    if is_admin_or_superuser(user):
        return {"is_deleted": {"$ne": True}}

    variants = get_user_id_variants(user.id)
    return {
        "$or": [
            {"created_by_id": {"$in": variants}},
            {"co_teachers": {"$in": variants}}
        ],
        "is_deleted": {"$ne": True}
    }


@login_required(login_url="login")
def dashboard(request):
    """
    Teacher Dashboard with live stats from MongoDB (supports Co-Teachers).
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]

    # ── Stat Cards ──────────────────────────────────────────────
    total_subjects  = len(user_sub_ids)
    total_questions = questions_collection.count_documents({"subject_id": {"$in": user_sub_ids}, "is_deleted": {"$ne": True}})
    total_exams     = exams_collection.count_documents({"subject_id": {"$in": user_sub_ids}})
    total_students  = User.objects.filter(role="STUDENT").count()

    # ── Recent Exams (last 5) ────────────────────────────────────
    from datetime import timedelta
    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)

    recent_exams_cursor = exams_collection.find({"subject_id": {"$in": user_sub_ids}}).sort("created_at", -1).limit(5)
    recent_exams = []
    upcoming_exams = []

    for e in recent_exams_cursor:
        e["id"] = str(e["_id"])
        e["question_count"] = len(e.get("question_ids", []))
        sub_doc = subjects_collection.find_one({"_id": e.get("subject_id")})
        e["subject_name"] = sub_doc.get("name", "") if sub_doc else ""

        # Dynamic status
        start_str = e.get("start_time", "")
        end_str   = e.get("end_time", "")
        status    = "SCHEDULED"
        if start_str and end_str:
            try:
                dt_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%M")
                dt_end   = datetime.strptime(end_str,   "%Y-%m-%dT%H:%M")
                if now_ist < dt_start:
                    status = "SCHEDULED"
                elif dt_start <= now_ist <= dt_end:
                    status = "LIVE"
                else:
                    status = "COMPLETED"
            except Exception:
                pass
        e["dynamic_status"] = status
        recent_exams.append(e)
        if status == "SCHEDULED":
            upcoming_exams.append(e)

    # ── Recent Results (last 5) ──────────────────────────────────
    exam_ids = [e["_id"] for e in exams_collection.find({"subject_id": {"$in": user_sub_ids}}, {"_id": 1})]
    recent_results_cursor = results_collection.find(
        {"exam_id": {"$in": exam_ids}}
    ).sort("evaluated_at", -1).limit(5)

    recent_results = []
    for r in recent_results_cursor:
        exam_doc = exams_collection.find_one({"_id": r.get("exam_id")})
        student_user = User.objects.filter(id=r.get("student_id")).first()
        recent_results.append({
            "exam_title":    exam_doc.get("title", "") if exam_doc else "",
            "student_name":  (f"{student_user.first_name} {student_user.last_name}".strip() or student_user.username) if student_user else "Unknown",
            "score":         r.get("score", 0),
            "total_marks":   r.get("total_marks", 0),
            "percentage":    r.get("percentage", 0),
            "status":        r.get("status", ""),
        })

    # ── Pass Rate ────────────────────────────────────────────────
    total_results = results_collection.count_documents({"exam_id": {"$in": exam_ids}})
    total_passed  = results_collection.count_documents({"exam_id": {"$in": exam_ids}, "status": "PASSED"})
    pass_rate = round(total_passed / total_results * 100, 1) if total_results > 0 else 0

    return render(request, "teacher_dashboard.html", {
        "total_subjects":  total_subjects,
        "total_questions": total_questions,
        "total_exams":     total_exams,
        "total_students":  total_students,
        "recent_exams":    recent_exams,
        "upcoming_exams":  upcoming_exams[:3],
        "recent_results":  recent_results,
        "total_results":   total_results,
        "total_passed":    total_passed,
        "pass_rate":       pass_rate,
    })



# ==============================================================================
# SUBJECT VIEWS (Direct PyMongo Queries with Admin Bypass)
# ==============================================================================

@login_required(login_url="login")
def subjects(request):
    """
    Subject listing and creation using PyMongo directly.
    """
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        description = request.POST.get("description", "").strip()

        if name and code:
            # Check for duplicate code using PyMongo
            existing = subjects_collection.find_one({"code": code})
            if existing:
                messages.error(request, f"Subject code '{code}' already exists!")
            else:
                import uuid
                now = datetime.utcnow()
                invite_code = f"SUB-{uuid.uuid4().hex[:6].upper()}"
                subjects_collection.insert_one({
                    "name": name,
                    "code": code,
                    "description": description,
                    "invite_code": invite_code,
                    "co_teachers": [],
                    "created_by_id": request.user.id,
                    "created_at": now,
                    "updated_at": now,
                })
                messages.success(request, f"Subject '{name}' created successfully! Share Invite Code '{invite_code}' with co-teachers.")
                return redirect("subjects")
        else:
            messages.error(request, "Subject Name and Code are required!")

    # Fetch active subjects owned or co-taught by teacher (exclude soft-deleted)
    query = {"is_deleted": {"$ne": True}}
    if not is_admin_or_superuser(request.user):
        query["$or"] = [{"created_by_id": request.user.id}, {"co_teachers": request.user.id}]

    cursor = subjects_collection.find(query).sort("created_at", -1)
    user_subjects = []
    import uuid
    for doc in cursor:
        doc["id"] = str(doc["_id"])
        # Ensure invite code exists for older subjects
        if not doc.get("invite_code"):
            code_gen = f"SUB-{uuid.uuid4().hex[:6].upper()}"
            subjects_collection.update_one({"_id": doc["_id"]}, {"$set": {"invite_code": code_gen, "co_teachers": []}})
            doc["invite_code"] = code_gen

        doc["is_owner"] = (doc.get("created_by_id") == request.user.id)
        doc["co_teacher_count"] = len(doc.get("co_teachers", []))
        user_subjects.append(doc)

    return render(request, "subjects.html", {
        "subjects": user_subjects,
    })


@login_required(login_url="login")
def join_subject(request):
    """
    Allows a teacher to join and collaborate on a subject by entering its unique Invite Code.
    """
    if request.method == "POST":
        code = request.POST.get("invite_code", "").strip().upper()
        if not code:
            messages.error(request, "Please enter a valid Subject Invite Code.")
            return redirect("subjects")

        sub_doc = subjects_collection.find_one({"invite_code": code, "is_deleted": {"$ne": True}})
        if not sub_doc:
            messages.error(request, f"No subject found matching Invite Code '{code}'. Please check and try again.")
            return redirect("subjects")

        if sub_doc.get("created_by_id") == request.user.id:
            messages.info(request, f"You are the owner of subject '{sub_doc['name']}'.")
            return redirect("subjects")

        if request.user.id in sub_doc.get("co_teachers", []):
            messages.info(request, f"You are already a Co-Teacher for '{sub_doc['name']}'.")
            return redirect("subjects")

        subjects_collection.update_one(
            {"_id": sub_doc["_id"]},
            {"$addToSet": {"co_teachers": request.user.id}}
        )
        messages.success(request, f"🎉 Success! You joined subject '{sub_doc['name']}' ({sub_doc['code']}) as a Co-Teacher.")
    return redirect("subjects")


@login_required(login_url="login")
@require_teacher_subject_access
def edit_subject(request, subject_id):
    """
    Edit Subject via PyMongo using Tenant Validation Decorator.
    """
    subject = getattr(request, "subject_doc", None)
    if not subject:
        messages.error(request, "Subject not found or access denied.")
        return redirect("subjects")

    obj_id = subject["_id"]

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        description = request.POST.get("description", "").strip()

        if name and code:
            subjects_collection.update_one(
                {"_id": obj_id},
                {"$set": {
                    "name": name,
                    "code": code,
                    "description": description,
                    "updated_at": datetime.utcnow(),
                }}
            )
            messages.success(request, f"Subject '{name}' updated successfully!")
            return redirect("subjects")
        else:
            messages.error(request, "Name and Code are required!")

    subject["id"] = str(subject["_id"])
    return render(request, "edit_subject.html", {
        "subject": subject,
    })


@login_required(login_url="login")
@require_teacher_subject_access
def delete_subject(request, subject_id):
    """
    Deletes subject and cleans up all associated scheduled exams,
    syllabus units, and questions using Tenant Access Validation Decorator.
    """
    if request.method == "POST":
        try:
            subject = getattr(request, "subject_doc", None)
            if subject:
                obj_id = subject["_id"]
                # 1. Delete the Subject document
                subjects_collection.delete_one({"_id": obj_id})
                # 2. Delete all scheduled exams for this subject
                exams_collection.delete_many({"subject_id": obj_id})
                # 3. Delete all syllabus units for this subject
                syllabus_collection.delete_many({"subject_id": obj_id})
                # 4. Delete all questions for this subject
                questions_collection.delete_many({"subject_id": obj_id})

                messages.success(request, f"Subject '{subject['name']}' and all its scheduled exams, syllabus units, and questions were deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting subject: {str(e)}")

    return redirect("subjects")


# ==============================================================================
# SYLLABUS VIEWS (Direct PyMongo Queries with Admin Bypass)
# ==============================================================================

@login_required(login_url="login")
def syllabus(request):
    """
    Syllabus listing and manual unit creation via PyMongo.
    """
    selected_subject_id = request.GET.get("subject", "")
    sub_query = get_teacher_subjects_query(request.user)
    user_subjects_cursor = subjects_collection.find(sub_query)
    user_subjects = []
    for s in user_subjects_cursor:
        s["id"] = str(s["_id"])
        user_subjects.append(s)

    if request.method == "POST":
        sub_id_str = request.POST.get("subject", "")
        unit_num_str = request.POST.get("unit_number", "1")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()

        if sub_id_str and title:
            try:
                sub_obj_id = ObjectId(sub_id_str)
                unit_num = int(unit_num_str)
                now = datetime.utcnow()

                syllabus_collection.insert_one({
                    "subject_id": sub_obj_id,
                    "unit_number": unit_num,
                    "title": title,
                    "description": description,
                    "created_at": now,
                    "updated_at": now,
                })
                messages.success(request, f"Unit {unit_num} ({title}) added successfully!")
                return redirect(f"/teacher/syllabus/?subject={sub_id_str}")
            except Exception as e:
                messages.error(request, f"Failed to add unit: {str(e)}")
        else:
            messages.error(request, "Subject and Unit Title are required!")

    # Fetch syllabus units via PyMongo
    query = {}
    if selected_subject_id:
        try:
            query["subject_id"] = ObjectId(selected_subject_id)
        except Exception:
            pass
    else:
        # Filter to units belonging to subjects owned by request.user / admin
        subject_ids = [s["_id"] for s in user_subjects]
        query["subject_id"] = {"$in": subject_ids}

    units_cursor = syllabus_collection.find(query).sort([("unit_number", 1)])
    units = []
    for u in units_cursor:
        u["id"] = str(u["_id"])

        # Attach subject info via PyMongo
        sub_doc = subjects_collection.find_one({"_id": u["subject_id"]})
        if sub_doc:
            u["subject"] = {
                "name": sub_doc.get("name", ""),
                "code": sub_doc.get("code", ""),
                "id": str(sub_doc["_id"])
            }
        units.append(u)

    return render(request, "syllabus.html", {
        "units": units,
        "subjects": user_subjects,
        "selected_subject_id": selected_subject_id,
    })


@login_required(login_url="login")
def edit_syllabus(request, unit_id):
    """
    Edit Syllabus Unit via PyMongo.
    """
    try:
        obj_id = ObjectId(unit_id)
    except Exception:
        messages.error(request, "Invalid Unit ID")
        return redirect("syllabus")

    unit = syllabus_collection.find_one({"_id": obj_id})
    if not unit:
        messages.error(request, "Unit not found.")
        return redirect("syllabus")

    sub_query = get_teacher_subjects_query(request.user)
    user_subjects_cursor = subjects_collection.find(sub_query)
    user_subjects = [dict(s, id=str(s["_id"])) for s in user_subjects_cursor]

    if request.method == "POST":
        sub_id_str = request.POST.get("subject", "")
        unit_num_str = request.POST.get("unit_number", "1")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()

        if title:
            try:
                syllabus_collection.update_one(
                    {"_id": obj_id},
                    {"$set": {
                        "subject_id": ObjectId(sub_id_str) if sub_id_str else unit["subject_id"],
                        "unit_number": int(unit_num_str),
                        "title": title,
                        "description": description,
                        "updated_at": datetime.utcnow(),
                    }}
                )
                messages.success(request, f"Unit updated successfully!")
                return redirect(f"/teacher/syllabus/?subject={sub_id_str}")
            except Exception as e:
                messages.error(request, f"Error updating unit: {str(e)}")

    unit["id"] = str(unit["_id"])
    unit["subject_id_str"] = str(unit["subject_id"])

    return render(request, "edit_syllabus.html", {
        "unit": unit,
        "subjects": user_subjects,
    })


@login_required(login_url="login")
def delete_syllabus(request, unit_id):
    """
    Delete Syllabus Unit via PyMongo.
    """
    if request.method == "POST":
        try:
            obj_id = ObjectId(unit_id)
            unit = syllabus_collection.find_one({"_id": obj_id})
            if unit:
                sub_id = str(unit["subject_id"])
                syllabus_collection.delete_one({"_id": obj_id})
                messages.success(request, "Syllabus unit deleted successfully.")
                return redirect(f"/teacher/syllabus/?subject={sub_id}")
        except Exception as e:
            messages.error(request, f"Error deleting unit: {str(e)}")

    return redirect("syllabus")


@login_required(login_url="login")
def upload_syllabus_pdf(request):
    """
    Upload PDF, parse text, and store syllabus units directly in MongoDB via PyMongo.
    """
    if request.method == "POST" and request.FILES.get("pdf_file"):
        subject_id_str = request.POST.get("subject_id")
        try:
            sub_obj_id = ObjectId(subject_id_str)
            query = get_teacher_subjects_query(request.user)
            query["_id"] = sub_obj_id

            subject = subjects_collection.find_one(query)
            if not subject:
                messages.error(request, "Subject not found or access denied.")
                return redirect("syllabus")

            pdf_file = request.FILES["pdf_file"]
            extracted_units = extract_syllabus_from_pdf(pdf_file)

            # Clear old syllabus units for this subject via PyMongo
            syllabus_collection.delete_many({"subject_id": sub_obj_id})

            now = datetime.utcnow()
            for u_data in extracted_units:
                syllabus_collection.insert_one({
                    "subject_id": sub_obj_id,
                    "unit_number": u_data["unit_number"],
                    "title": u_data["title"][:200],
                    "description": u_data["description"],
                    "created_at": now,
                    "updated_at": now,
                })

            messages.success(
                request,
                f"Successfully extracted {len(extracted_units)} syllabus units via PyMongo into {subject['name']}!",
            )
            return redirect(f"/teacher/syllabus/?subject={subject_id_str}")
        except Exception as e:
            messages.error(request, f"Failed to parse PDF: {str(e)}")
            return redirect("syllabus")

    return redirect("syllabus")


# ==============================================================================
# QUESTION BANK VIEWS (Direct PyMongo Queries with Admin Bypass)
# ==============================================================================

@login_required(login_url="login")
def question_bank(request):
    """
    Question Bank listing and filtering via PyMongo.
    """
    selected_subject_id = request.GET.get("subject", "")
    selected_type = request.GET.get("type", "")
    selected_difficulty = request.GET.get("difficulty", "")

    sub_query = get_teacher_subjects_query(request.user)
    user_subjects_cursor = subjects_collection.find(sub_query)
    user_subjects = [dict(s, id=str(s["_id"])) for s in user_subjects_cursor]

    user_sub_ids = [s["_id"] for s in user_subjects_cursor]

    query = {"is_deleted": {"$ne": True}}
    if selected_subject_id:
        try:
            query["subject_id"] = ObjectId(selected_subject_id)
        except Exception:
            pass
    else:
        query["subject_id"] = {"$in": user_sub_ids}
    if selected_type:
        query["question_type"] = selected_type
    if selected_difficulty:
        query["difficulty"] = selected_difficulty

    cursor = questions_collection.find(query).sort("created_at", -1)
    questions = []
    for q in cursor:
        q["id"] = str(q["_id"])
        sub_doc = subjects_collection.find_one({"_id": q.get("subject_id")})
        if sub_doc:
            q["subject"] = {"name": sub_doc.get("name", ""), "code": sub_doc.get("code", "")}
        questions.append(q)

    return render(request, "question_bank.html", {
        "questions": questions,
        "subjects": user_subjects,
        "selected_subject_id": selected_subject_id,
        "selected_type": selected_type,
        "selected_difficulty": selected_difficulty,
        "question_types": [
            ("MCQ", "Multiple Choice (MCQ)"),
            ("TRUE_FALSE", "True / False"),
            ("DESCRIPTIVE", "Descriptive / Short Answer"),
        ],
        "difficulties": [
            ("EASY", "Easy"),
            ("MEDIUM", "Medium"),
            ("HARD", "Hard"),
        ],
    })


@login_required(login_url="login")
def add_question(request):
    """
    Add Question via PyMongo.
    """
    if request.method == "POST":
        sub_id_str = request.POST.get("subject", "")
        unit_id_str = request.POST.get("unit", "")
        q_type = request.POST.get("question_type", "MCQ")
        difficulty = request.POST.get("difficulty", "MEDIUM")
        marks_str = request.POST.get("marks", "1")
        question_text = request.POST.get("question_text", "").strip()
        option_a = request.POST.get("option_a", "").strip()
        option_b = request.POST.get("option_b", "").strip()
        option_c = request.POST.get("option_c", "").strip()
        option_d = request.POST.get("option_d", "").strip()
        correct_answer = request.POST.get("correct_answer", "").strip()

        if sub_id_str and question_text:
            try:
                now = datetime.utcnow()
                doc = {
                    "subject_id": ObjectId(sub_id_str),
                    "unit_id": ObjectId(unit_id_str) if unit_id_str else None,
                    "question_type": q_type,
                    "difficulty": difficulty,
                    "marks": int(marks_str),
                    "question_text": question_text,
                    "option_a": option_a,
                    "option_b": option_b,
                    "option_c": option_c,
                    "option_d": option_d,
                    "correct_answer": correct_answer,
                    "created_by_id": request.user.id,
                    "created_at": now,
                    "updated_at": now,
                }
                questions_collection.insert_one(doc)
                messages.success(request, "Question added via PyMongo to Question Bank!")
                return redirect(f"/teacher/question_bank/?subject={sub_id_str}")
            except Exception as e:
                messages.error(request, f"Error saving question: {str(e)}")
        else:
            messages.error(request, "Subject and Question Text are required!")

    return redirect("question_bank")


@login_required(login_url="login")
def edit_question(request, question_id):
    """
    Edit Question via PyMongo.
    """
    try:
        obj_id = ObjectId(question_id)
    except Exception:
        messages.error(request, "Invalid Question ID")
        return redirect("question_bank")

    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]

    query = {"_id": obj_id}
    if not is_admin_or_superuser(request.user):
        query["subject_id"] = {"$in": user_sub_ids}

    q = questions_collection.find_one(query)
    if not q:
        messages.error(request, "Question not found or access denied.")
        return redirect("question_bank")

    user_subjects_cursor = subjects_collection.find(sub_query)
    user_subjects = [dict(s, id=str(s["_id"])) for s in user_subjects_cursor]

    if request.method == "POST":
        sub_id_str = request.POST.get("subject", "")
        unit_id_str = request.POST.get("unit", "")
        q_type = request.POST.get("question_type", "MCQ")
        difficulty = request.POST.get("difficulty", "MEDIUM")
        marks_str = request.POST.get("marks", "1")
        question_text = request.POST.get("question_text", "").strip()
        option_a = request.POST.get("option_a", "").strip()
        option_b = request.POST.get("option_b", "").strip()
        option_c = request.POST.get("option_c", "").strip()
        option_d = request.POST.get("option_d", "").strip()
        correct_answer = request.POST.get("correct_answer", "").strip()

        if question_text:
            try:
                questions_collection.update_one(
                    {"_id": obj_id},
                    {"$set": {
                        "subject_id": ObjectId(sub_id_str) if sub_id_str else q["subject_id"],
                        "unit_id": ObjectId(unit_id_str) if unit_id_str else None,
                        "question_type": q_type,
                        "difficulty": difficulty,
                        "marks": int(marks_str),
                        "question_text": question_text,
                        "option_a": option_a,
                        "option_b": option_b,
                        "option_c": option_c,
                        "option_d": option_d,
                        "correct_answer": correct_answer,
                        "updated_at": datetime.utcnow(),
                    }}
                )
                messages.success(request, "Question updated successfully via PyMongo!")
                return redirect(f"/teacher/question_bank/?subject={sub_id_str}")
            except Exception as e:
                messages.error(request, f"Error updating question: {str(e)}")

    q["id"] = str(q["_id"])
    q["subject_id_str"] = str(q["subject_id"])
    q["unit_id_str"] = str(q["unit_id"]) if q.get("unit_id") else ""

    return render(request, "edit_question.html", {
        "question": q,
        "subjects": user_subjects,
    })


@login_required(login_url="login")
def delete_question(request, question_id):
    """
    Deletes Question via PyMongo.
    If the question is already used in a scheduled/past exam, it is soft-deleted (is_deleted=True)
    so it disappears from the Question Bank list, BUT remains intact for the scheduled exam!
    If not in any exam, it is permanently hard-deleted.
    """
    if request.method == "POST":
        try:
            obj_id = ObjectId(question_id)
            sub_query = get_teacher_subjects_query(request.user)
            user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]

            query = {"_id": obj_id}
            if not is_admin_or_superuser(request.user):
                query["subject_id"] = {"$in": user_sub_ids}

            q = questions_collection.find_one(query)
            if q:
                sub_id = str(q["subject_id"])
                
                # Check if question is used in any scheduled/live/completed exam
                linked_exam = exams_collection.find_one({"question_ids": obj_id})

                if linked_exam:
                    # Soft Delete: KEEP question document for scheduled exam, hide from Question Bank
                    questions_collection.update_one(
                        {"_id": obj_id},
                        {"$set": {
                            "is_deleted": True,
                            "deleted_at": datetime.utcnow()
                        }}
                    )
                    messages.success(request, f"Question is used in exam '{linked_exam['title']}' — soft-deleted from Question Bank to preserve exam integrity.")
                else:
                    # Hard Delete if not used in any exam
                    questions_collection.delete_one({"_id": obj_id})
                    messages.success(request, "Question deleted successfully from Question Bank.")

                return redirect(f"/teacher/question_bank/?subject={sub_id}")
        except Exception as e:
            messages.error(request, f"Error deleting question: {str(e)}")

    return redirect("question_bank")


# ==============================================================================
# AI QUESTION GENERATOR VIEWS (Enterprise Service Layer with Admin Bypass)
# ==============================================================================

from .validators import validate_teacher_subject_access, validate_teacher_unit_access, sanitize_input_string
from .services.ai_service import AIQuestionGeneratorService


@login_required(login_url="login")
@require_teacher_subject_access
def ai_question_generator(request):
    """
    Renders AI Question Generator interface and processes question generation requests
    using Tenant Validation Decorator.
    """
    sub_query = get_teacher_subjects_query(request.user)
    user_subjects_cursor = list(subjects_collection.find(sub_query))
    user_subjects = [dict(s, id=str(s["_id"])) for s in user_subjects_cursor]

    generated_questions = []
    selected_subject_id = request.GET.get("subject", "")
    selected_unit_id = request.GET.get("unit", "")

    if request.method == "POST":
        selected_subject_id = request.POST.get("subject_id", "")
        selected_unit_id = request.POST.get("unit_id", "")
        count = request.POST.get("count", "5")
        q_type = request.POST.get("question_type", "MCQ")
        difficulty = request.POST.get("difficulty", "MEDIUM")
        custom_prompt = sanitize_input_string(request.POST.get("custom_prompt", ""), max_length=500)

        # Tenant Authorization Check via Decorator request.subject_doc or manual fallback
        sub_doc = getattr(request, "subject_doc", None)
        if not sub_doc:
            is_valid_sub, sub_doc, sub_err = validate_teacher_subject_access(selected_subject_id, request.user.id)
            if not is_valid_sub:
                messages.error(request, sub_err)
                return redirect("ai_question_generator")

        # Optional Unit Authorization Check
        syllabus_topics = []
        if selected_unit_id:
            is_valid_unit, unit_doc, unit_err = validate_teacher_unit_access(selected_unit_id, request.user.id)
            if is_valid_unit and unit_doc:
                syllabus_topics = [f"Unit {unit_doc.get('unit_number')}: {unit_doc.get('title')}", unit_doc.get('description', '')]
            elif unit_err:
                messages.error(request, unit_err)
                return redirect("ai_question_generator")
        else:
            # Gather all unit topics for the subject via PyMongo
            units_cursor = syllabus_collection.find({"subject_id": sub_doc["_id"]})
            for u in units_cursor:
                syllabus_topics.append(f"Unit {u.get('unit_number')}: {u.get('title')} - {u.get('description', '')}")

        # Execute AI Generation via Service Layer
        ai_service = AIQuestionGeneratorService()
        generated_questions = ai_service.generate_questions(
            subject_name=sub_doc["name"],
            syllabus_topics=syllabus_topics,
            count=int(count) if count.isdigit() else 5,
            question_type=q_type,
            difficulty=difficulty,
            custom_prompt=custom_prompt,
        )

        messages.success(request, f"Generated {len(generated_questions)} questions! Review and save them below.")

    # Fetch available units for selected subject (or first subject) to populate unit dropdown
    user_units = []
    active_sub_id = selected_subject_id or (user_subjects[0]["id"] if user_subjects else "")
    if active_sub_id:
        try:
            units_cursor = syllabus_collection.find({"subject_id": ObjectId(active_sub_id)}).sort("unit_number", 1)
            for u in units_cursor:
                u["id"] = str(u["_id"])
                user_units.append(u)
        except Exception:
            pass

    return render(request, "ai_question_generator.html", {
        "subjects": user_subjects,
        "units": user_units,
        "selected_subject_id": selected_subject_id or active_sub_id,
        "selected_unit_id": selected_unit_id,
        "generated_questions": generated_questions,
        "question_types": [
            ("MCQ", "Multiple Choice (MCQ)"),
            ("TRUE_FALSE", "True / False"),
            ("DESCRIPTIVE", "Descriptive / Short Answer"),
        ],
        "difficulties": [
            ("EASY", "Easy"),
            ("MEDIUM", "Medium"),
            ("HARD", "Hard"),
        ],
    })


@login_required(login_url="login")
@require_teacher_subject_access
def save_generated_questions(request):
    """
    Bulk inserts approved AI-generated questions into MongoDB via PyMongo using Tenant Validation Decorator.
    """
    if request.method == "POST":
        subject_id_str = request.POST.get("subject_id", "")
        unit_id_str = request.POST.get("unit_id", "")
        payload_json_str = request.POST.get("questions_payload", "")

        sub_doc = getattr(request, "subject_doc", None)
        if not sub_doc:
            is_valid_sub, sub_doc, sub_err = validate_teacher_subject_access(subject_id_str, request.user.id)
            if not is_valid_sub:
                messages.error(request, sub_err)
                return redirect("ai_question_generator")

        try:
            questions_data = json.loads(payload_json_str)
            if not questions_data:
                messages.warning(request, "No questions were selected for saving.")
                return redirect("ai_question_generator")

            # Get user selected question indices (e.g. ['0', '2', '4'])
            selected_indices = request.POST.getlist("selected_ai_questions")
            now = datetime.utcnow()
            docs_to_insert = []

            for idx, q in enumerate(questions_data):
                idx_str = str(idx)
                # If checkboxes were submitted, save only checked ones
                if selected_indices and idx_str not in selected_indices:
                    continue

                custom_marks_raw = request.POST.get(f"marks_{idx}", str(q.get("marks", 2)))
                custom_marks = int(custom_marks_raw) if custom_marks_raw.isdigit() and int(custom_marks_raw) > 0 else 2

                docs_to_insert.append({
                    "subject_id": sub_doc["_id"],
                    "unit_id": ObjectId(unit_id_str) if unit_id_str else None,
                    "question_type": q.get("question_type", "MCQ"),
                    "difficulty": q.get("difficulty", "MEDIUM"),
                    "marks": custom_marks,
                    "question_text": q.get("question_text", "").strip(),
                    "option_a": q.get("option_a", "").strip(),
                    "option_b": q.get("option_b", "").strip(),
                    "option_c": q.get("option_c", "").strip(),
                    "option_d": q.get("option_d", "").strip(),
                    "correct_answer": q.get("correct_answer", "").strip(),
                    "created_by_id": request.user.id,
                    "created_at": now,
                    "updated_at": now,
                })

            # Enterprise PyMongo Bulk Insert
            if docs_to_insert:
                questions_collection.insert_many(docs_to_insert)
                messages.success(request, f"Successfully saved {len(docs_to_insert)} selected AI question(s) into Question Bank!")
                return redirect(f"/teacher/question_bank/?subject={subject_id_str}")
            else:
                messages.warning(request, "No questions were selected to be saved.")

        except Exception as e:
            messages.error(request, f"Failed to save questions: {str(e)}")

    return redirect("ai_question_generator")


# ==============================================================================
# EXAM CREATION & SCHEDULING VIEWS (Dual Assembly Engine with Admin Bypass)
# ==============================================================================

@login_required(login_url="login")
def create_test(request):
    """
    Creates an Exam using either Mode 1 (Manual Selection) or Mode 2 (System Auto-Generation).
    """
    sub_query = get_teacher_subjects_query(request.user)
    user_subjects_cursor = subjects_collection.find(sub_query)
    user_subjects = [dict(s, id=str(s["_id"])) for s in user_subjects_cursor]

    selected_subject_id = request.GET.get("subject", "")
    if not selected_subject_id and user_subjects:
        selected_subject_id = user_subjects[0]["id"]

    # Fetch questions available for manual assembly
    questions = []
    if selected_subject_id:
        try:
            q_query = {"subject_id": ObjectId(selected_subject_id), "is_deleted": {"$ne": True}}
            q_cursor = questions_collection.find(q_query).sort("created_at", -1)
            for q in q_cursor:
                q["id"] = str(q["_id"])
                questions.append(q)
        except Exception:
            pass

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        sub_id_str = request.POST.get("subject_id", "")
        duration_str = request.POST.get("duration_minutes", "60")
        passing_marks_str = request.POST.get("passing_marks", "20")
        access_code = request.POST.get("access_code", "").strip()
        start_time_str = request.POST.get("start_time", "")
        end_time_str = request.POST.get("end_time", "")
        assembly_mode = request.POST.get("assembly_mode", "MANUAL")  # MANUAL vs AUTO

        is_valid_sub, sub_doc, sub_err = validate_teacher_subject_access(sub_id_str, request.user.id)
        if not is_valid_sub:
            messages.error(request, sub_err)
            return redirect("create_test")

        if not title:
            messages.error(request, "Exam Title is required.")
            return redirect("create_test")

        if not start_time_str or not end_time_str:
            messages.error(request, "Start Time and End Time (Exam Schedule Window) are required and mandatory.")
            return redirect(f"/teacher/create_test/?subject={sub_id_str}")

        selected_q_ids = []
        total_marks = 0

        if assembly_mode == "MANUAL":
            raw_q_ids = request.POST.getlist("selected_questions")
            if not raw_q_ids:
                messages.error(request, "Please select at least one question for manual exam assembly.")
                return redirect(f"/teacher/create_test/?subject={sub_id_str}")

            for qid in raw_q_ids:
                try:
                    q_obj_id = ObjectId(qid)
                    q_doc = questions_collection.find_one({"_id": q_obj_id})
                    if q_doc:
                        selected_q_ids.append(q_obj_id)
                        total_marks += int(q_doc.get("marks", 1))
                except Exception:
                    pass

        elif assembly_mode == "AUTO":
            num_easy = int(request.POST.get("num_easy", 0) or 0)
            num_medium = int(request.POST.get("num_medium", 0) or 0)
            num_hard = int(request.POST.get("num_hard", 0) or 0)

            def sample_questions(difficulty, count):
                if count <= 0:
                    return []
                pipeline = [
                    {"$match": {"subject_id": sub_doc["_id"], "difficulty": difficulty}},
                    {"$sample": {"size": count}}
                ]
                return list(questions_collection.aggregate(pipeline))

            easy_docs = sample_questions("EASY", num_easy)
            medium_docs = sample_questions("MEDIUM", num_medium)
            hard_docs = sample_questions("HARD", num_hard)

            # Check for question shortages in Question Bank
            shortages = []
            if len(easy_docs) < num_easy:
                shortages.append(f"Easy: requested {num_easy}, but only {len(easy_docs)} available")
            if len(medium_docs) < num_medium:
                shortages.append(f"Medium: requested {num_medium}, but only {len(medium_docs)} available")
            if len(hard_docs) < num_hard:
                shortages.append(f"Hard: requested {num_hard}, but only {len(hard_docs)} available")

            if shortages:
                messages.warning(request, f"Notice: Question Bank shortage detected! ({', '.join(shortages)}). Available questions were assembled.")

            all_auto_docs = easy_docs + medium_docs + hard_docs
            if not all_auto_docs:
                messages.error(request, "No questions matched your auto-generation rules in Question Bank. Please add questions first.")
                return redirect(f"/teacher/create_test/?subject={sub_id_str}")

            for q_doc in all_auto_docs:
                selected_q_ids.append(q_doc["_id"])
                total_marks += int(q_doc.get("marks", 1))

        now = datetime.utcnow()
        exam_doc = {
            "title": title,
            "subject_id": sub_doc["_id"],
            "created_by_id": request.user.id,
            "duration_minutes": int(duration_str) if duration_str.isdigit() else 60,
            "total_marks": total_marks if total_marks > 0 else 50,
            "passing_marks": int(passing_marks_str) if passing_marks_str.isdigit() else 20,
            "access_code": access_code or "EXAM123",
            "start_time": start_time_str,
            "end_time": end_time_str,
            "question_ids": selected_q_ids,
            "assembly_mode": assembly_mode,
            "status": "SCHEDULED",
            "created_at": now,
            "updated_at": now,
        }

        exams_collection.insert_one(exam_doc)
        messages.success(request, f"Exam '{title}' created & scheduled successfully with {len(selected_q_ids)} questions ({total_marks} Marks)!")
        return redirect("scheduled_exams")

    return render(request, "create_test.html", {
        "subjects": user_subjects,
        "selected_subject_id": selected_subject_id,
        "questions": questions,
    })


@login_required(login_url="login")
def scheduled_exams(request):
    """
    Lists all scheduled and completed exams.
    """
    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]
    exam_query = {} if is_admin_or_superuser(request.user) else {"subject_id": {"$in": user_sub_ids}}
    cursor = exams_collection.find(exam_query).sort("created_at", -1)
    exams = []

    # The machine clock runs in UTC but start_time/end_time are stored as IST
    # strings from the browser's datetime-local input (e.g. "2026-07-22T21:36").
    # We add the IST offset (+05:30 = 330 minutes) to UTC now() so both sides
    # of the comparison are in IST with no timezone objects involved.
    from datetime import timedelta
    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)

    for e in cursor:
        e["id"] = str(e["_id"])
        e["question_count"] = len(e.get("question_ids", []))

        status = e.get("status", "SCHEDULED")
        start_str = e.get("start_time", "")
        end_str = e.get("end_time", "")

        if start_str and end_str:
            try:
                # Parse the stored "YYYY-MM-DDTHH:MM" strings as naive local datetimes
                dt_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%M")
                dt_end = datetime.strptime(end_str, "%Y-%m-%dT%H:%M")

                if now_ist < dt_start:
                    status = "SCHEDULED"
                elif dt_start <= now_ist <= dt_end:
                    status = "LIVE"
                else:
                    status = "COMPLETED"

                e["formatted_start"] = dt_start.strftime("%b %d, %Y - %I:%M %p")
                e["formatted_end"] = dt_end.strftime("%b %d, %Y - %I:%M %p")
            except Exception:
                e["formatted_start"] = start_str
                e["formatted_end"] = end_str
        else:
            e["formatted_start"] = start_str or "Anytime"
            e["formatted_end"] = end_str or "No deadline"

        e["dynamic_status"] = status

        sub_doc = subjects_collection.find_one({"_id": e.get("subject_id")})
        if sub_doc:
            e["subject"] = {"name": sub_doc.get("name", ""), "code": sub_doc.get("code", "")}
        exams.append(e)

    return render(request, "scheduled_exams.html", {
        "exams": exams,
    })


@login_required(login_url="login")
def delete_exam(request, exam_id):
    """
    Deletes an exam via PyMongo.
    """
    if request.method == "POST":
        try:
            obj_id = ObjectId(exam_id)
            sub_query = get_teacher_subjects_query(request.user)
            user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]

            query = {"_id": obj_id}
            if not is_admin_or_superuser(request.user):
                query["subject_id"] = {"$in": user_sub_ids}

            exams_collection.delete_one(query)
            messages.success(request, "Exam deleted successfully.")
        except Exception as e:
            messages.error(request, f"Failed to delete exam: {str(e)}")

    return redirect("scheduled_exams")


# ==============================================================================
# SUBMISSIONS, RESULTS, ANALYTICS, STUDENTS VIEWS (Direct PyMongo Queries)
# ==============================================================================

@login_required(login_url="login")
def student_submissions(request):
    """
    Lists student submissions for exams created by this teacher (or all for ADMIN).
    """
    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]
    exam_query = {} if is_admin_or_superuser(request.user) else {"subject_id": {"$in": user_sub_ids}}
    teacher_exams = list(exams_collection.find(exam_query, {"_id": 1}))
    teacher_exam_ids = [e["_id"] for e in teacher_exams]

    submissions = []
    # Fetch all attempts (including incomplete/abandoned ones)
    attempts = attempts_collection.find({"exam_id": {"$in": teacher_exam_ids}}).sort("started_at", -1)

    from django.contrib.auth import get_user_model
    User = get_user_model()

    for att in attempts:
        # Fetch Student User Details
        student_user = User.objects.filter(id=att.get("student_id")).first()
        exam_doc = exams_collection.find_one({"_id": att.get("exam_id")})
        res_doc = results_collection.find_one({"attempt_id": att["_id"]})
        
        is_submitted = att.get("is_submitted", False)

        if student_user and exam_doc:
                if is_submitted:
                    score = res_doc.get("score", 0) if res_doc else 0
                    total_marks = res_doc.get("total_marks", 0) if res_doc else 0
                    percentage = round(score / total_marks * 100, 1) if total_marks > 0 else 0
                    status = res_doc.get("status", "PENDING") if res_doc else "PENDING"
                    submitted_at = att.get("submitted_at")
                else:
                    score = 0
                    total_marks = 0
                    percentage = 0
                    status = "ABANDONED"
                    submitted_at = att.get("started_at") # show started time

                submissions.append({
                    "id": str(att["_id"]),
                    "student_name": f"{student_user.first_name} {student_user.last_name}".strip() or student_user.username,
                    "student_username": student_user.username,
                    "exam_title": exam_doc.get("title", ""),
                    "submitted_at": submitted_at,
                    "score": score,
                    "total_marks": total_marks,
                    "percentage": percentage,
                    "status": status,
                    "is_submitted": is_submitted,
                })

    return render(request, "student_submissions.html", {"submissions": submissions})


@login_required(login_url="login")
def teacher_submission_review(request, attempt_id):
    """
    Detailed answer sheet inspection view for teachers.
    """
    try:
        att_obj_id = ObjectId(attempt_id)
    except Exception:
        return redirect("student_submissions")

    attempt = attempts_collection.find_one({"_id": att_obj_id})
    if not attempt:
        messages.error(request, "Submission attempt not found.")
        return redirect("student_submissions")

    exam_doc = exams_collection.find_one({"_id": attempt.get("exam_id")})
    res_doc = results_collection.find_one({"attempt_id": att_obj_id})

    # Tenant authorization check for teacher
    if not is_admin_or_superuser(request.user) and exam_doc and exam_doc.get("created_by_id") != request.user.id:
        messages.error(request, "Access denied to this student submission.")
        return redirect("student_submissions")

    subject_name = "General"
    subject_code = ""
    if exam_doc:
        sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
        if sub_doc:
            subject_name = sub_doc.get("name", "General")
            subject_code = sub_doc.get("code", "")

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

    return render(request, "teacher_submission_review.html", {
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
def teacher_submission_review(request, attempt_id):
    """
    Detailed answer sheet inspection view for teachers.
    """
    try:
        att_obj_id = ObjectId(attempt_id)
    except Exception:
        return redirect("student_submissions")

    attempt = attempts_collection.find_one({"_id": att_obj_id})
    if not attempt:
        messages.error(request, "Submission attempt not found.")
        return redirect("student_submissions")

    exam_doc = exams_collection.find_one({"_id": attempt.get("exam_id")})
    res_doc = results_collection.find_one({"attempt_id": att_obj_id})

    # Tenant authorization check for teacher (owned OR co-taught subject)
    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]
    if not is_admin_or_superuser(request.user) and exam_doc and exam_doc.get("subject_id") not in user_sub_ids:
        messages.error(request, "Access denied to this student submission.")
        return redirect("student_submissions")

    subject_name = "General"
    subject_code = ""
    if exam_doc:
        sub_doc = subjects_collection.find_one({"_id": exam_doc.get("subject_id")})
        if sub_doc:
            subject_name = sub_doc.get("name", "General")
            subject_code = sub_doc.get("code", "")

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

    proctor_violations = attempt.get("proctor_violations", [])

    return render(request, "teacher_submission_review.html", {
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
        "proctor_violations": proctor_violations,
        "violation_count": len(proctor_violations),
    })


@login_required(login_url="login")
def results(request):
    """
    Lists overall exam results & gradebook for exams created by this teacher (or all for ADMIN).
    Groups records so each student has 1 row with all their attempts displayed side-by-side.
    """
    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]
    exam_query = {} if is_admin_or_superuser(request.user) else {"subject_id": {"$in": user_sub_ids}}
    teacher_exams = list(exams_collection.find(exam_query))

    from django.contrib.auth import get_user_model
    User = get_user_model()
    from collections import defaultdict

    exam_results = []
    for exam in teacher_exams:
        exam_res_cursor = list(results_collection.find({"exam_id": exam["_id"]}).sort("evaluated_at", 1))
        
        # Group results by student_id
        student_results_map = defaultdict(list)
        for r in exam_res_cursor:
            student_results_map[r.get("student_id")].append(r)

        student_scores = []
        passed_count = 0
        failed_count = 0

        for student_id, r_list in student_results_map.items():
            student_user = User.objects.filter(id=student_id).first()
            if not student_user:
                continue

            attempts_history = []
            for idx, r in enumerate(r_list, start=1):
                attempts_history.append({
                    "attempt_no": idx,
                    "score": r.get("score", 0),
                    "total_marks": r.get("total_marks", 0),
                    "percentage": r.get("percentage", 0),
                    "status": r.get("status", "FAILED"),
                })

            # Main row displays the latest attempt
            latest_r = r_list[-1]
            best_score = max(r.get("score", 0) for r in r_list)
            latest_status = latest_r.get("status", "FAILED")

            student_scores.append({
                "student_name": f"{student_user.first_name} {student_user.last_name}".strip() or student_user.username,
                "student_username": student_user.username,
                "score": latest_r.get("score", 0),
                "best_score": best_score,
                "total_marks": latest_r.get("total_marks", 0),
                "percentage": latest_r.get("percentage", 0),
                "status": latest_status,
                "attempts_history": attempts_history,
                "total_attempts": len(attempts_history),
            })

            if latest_status == "PASSED":
                passed_count += 1
            else:
                failed_count += 1

        # Sort students by highest percentage descending
        student_scores.sort(key=lambda s: s["percentage"], reverse=True)

        exam_results.append({
            "exam_title": exam.get("title", ""),
            "total_marks": exam.get("total_marks", 0),
            "passing_marks": exam.get("passing_marks", 0),
            "student_scores": student_scores,
            "passed_count": passed_count,
            "failed_count": failed_count,
        })

    return render(request, "results.html", {"exam_results": exam_results})


@login_required(login_url="login")
def analytics(request):
    """
    Advanced Analytics dashboard with Chart.js data for teachers / ADMIN.
    """
    exam_query = {} if is_admin_or_superuser(request.user) else {"created_by_id": request.user.id}
    teacher_exams = list(exams_collection.find(exam_query))
    teacher_exam_ids = [e["_id"] for e in teacher_exams]

    # ── Top-level metrics ────────────────────────────────────────
    total_exams    = len(teacher_exams)
    total_attempts = attempts_collection.count_documents({"exam_id": {"$in": teacher_exam_ids}, "is_submitted": True})
    total_passed   = results_collection.count_documents({"exam_id": {"$in": teacher_exam_ids}, "status": "PASSED"})
    total_failed   = results_collection.count_documents({"exam_id": {"$in": teacher_exam_ids}, "status": "FAILED"})
    pass_rate      = round(total_passed / total_attempts * 100, 1) if total_attempts > 0 else 0

    # ── Per-exam data for bar chart ──────────────────────────────
    exam_labels      = []
    avg_scores       = []
    passed_counts    = []
    failed_counts    = []

    for exam in teacher_exams:
        exam_results = list(results_collection.find({"exam_id": exam["_id"]}))
        if not exam_results:
            continue
        exam_labels.append(exam.get("title", "Untitled"))
        scores = [r.get("percentage", 0) for r in exam_results]
        avg_scores.append(round(sum(scores) / len(scores), 1))
        passed_counts.append(sum(1 for r in exam_results if r.get("status") == "PASSED"))
        failed_counts.append(sum(1 for r in exam_results if r.get("status") == "FAILED"))

    # ── Question type distribution (donut chart) ─────────────────
    q_query = {} if is_admin_or_superuser(request.user) else {"created_by_id": request.user.id}
    mcq_count        = questions_collection.count_documents({**q_query, "question_type": "MCQ"})
    truefalse_count  = questions_collection.count_documents({**q_query, "question_type": "TRUE_FALSE"})
    descriptive_count= questions_collection.count_documents({**q_query, "question_type": "DESCRIPTIVE"})

    # ── Score distribution buckets (histogram) ───────────────────
    all_results   = list(results_collection.find({"exam_id": {"$in": teacher_exam_ids}}))
    buckets       = [0, 0, 0, 0, 0]   # 0-20, 21-40, 41-60, 61-80, 81-100
    for r in all_results:
        pct = r.get("percentage", 0)
        if pct <= 20:   buckets[0] += 1
        elif pct <= 40: buckets[1] += 1
        elif pct <= 60: buckets[2] += 1
        elif pct <= 80: buckets[3] += 1
        else:           buckets[4] += 1

    import json
    return render(request, "analytics.html", {
        "total_exams":         total_exams,
        "total_attempts":      total_attempts,
        "total_passed":        total_passed,
        "total_failed":        total_failed,
        "pass_rate":           pass_rate,
        # Chart.js JSON data
        "exam_labels_json":    json.dumps(exam_labels),
        "avg_scores_json":     json.dumps(avg_scores),
        "passed_counts_json":  json.dumps(passed_counts),
        "failed_counts_json":  json.dumps(failed_counts),
        "qtype_labels_json":   json.dumps(["MCQ", "True/False", "Descriptive"]),
        "qtype_data_json":     json.dumps([mcq_count, truefalse_count, descriptive_count]),
        "bucket_labels_json":  json.dumps(["0–20%", "21–40%", "41–60%", "61–80%", "81–100%"]),
        "bucket_data_json":    json.dumps(buckets),
    })


@login_required(login_url="login")
def students(request):
    """
    Lists students registered in the system.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    student_list = User.objects.filter(role="STUDENT").order_index("username") if hasattr(User.objects.filter(role="STUDENT"), 'order_index') else User.objects.filter(role="STUDENT").order_by("username")

    return render(request, "students.html", {"students": student_list})


# ==============================================================================
# SETTINGS VIEW (Profile Details, Profile Picture, Password Change)
# ==============================================================================

@login_required(login_url="login")
def settings(request):
    """
    Teacher Settings: Profile Update & Password Change.
    """
    user = request.user

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "update_profile":
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            email = request.POST.get("email", "").strip()
            phone_number = request.POST.get("phone_number", "").strip()

            user.first_name = first_name
            user.last_name = last_name
            if email:
                user.email = email
            user.phone_number = phone_number

            if request.FILES.get("profile_picture"):
                user.profile_picture = request.FILES["profile_picture"]

            user.save()

            messages.success(request, "Profile details and picture updated successfully!")
            return redirect("settings")

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
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed successfully!")
                return redirect("settings")

    return render(request, "settings.html", {
        "user_obj": user,
    })


# ==============================================================================
# OPTION B — EXPORT RESULTS AS CSV
# ==============================================================================

@login_required(login_url="login")
def export_results_csv(request):
    """
    Exports all exam results for this teacher as a downloadable CSV file.
    Admin sees all results across all teachers.
    """
    import csv
    from django.http import HttpResponse
    from django.contrib.auth import get_user_model
    User = get_user_model()

    exam_query = {} if is_admin_or_superuser(request.user) else {"created_by_id": request.user.id}
    teacher_exams = list(exams_collection.find(exam_query))
    exam_ids = [e["_id"] for e in teacher_exams]
    exam_map = {str(e["_id"]): e.get("title", "Exam") for e in teacher_exams}

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="exam_results.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Student Name", "Username", "Roll Number", "PEN", "Exam Title",
        "Score", "Total Marks", "Percentage (%)", "Status", "Evaluated At"
    ])

    results_cursor = results_collection.find(
        {"exam_id": {"$in": exam_ids}}
    ).sort("evaluated_at", -1)

    for r in results_cursor:
        student = User.objects.filter(id=r.get("student_id")).first()
        student_name = (
            f"{student.first_name} {student.last_name}".strip() or student.username
        ) if student else "Unknown"
        username = student.username if student else "—"
        roll_number = getattr(student, 'roll_number', '—') or '—'
        pen = getattr(student, 'pen', '—') or '—'
        exam_title = exam_map.get(str(r.get("exam_id")), "—")

        writer.writerow([
            student_name,
            username,
            roll_number,
            pen,
            exam_title,
            r.get("score", 0),
            r.get("total_marks", 0),
            r.get("percentage", 0),
            r.get("status", ""),
            r.get("evaluated_at", "").strftime("%Y-%m-%d %H:%M:%S") if r.get("evaluated_at") else "",
        ])

    return response


# ==============================================================================
# OPTION C — EDIT EXAM
# ==============================================================================

@login_required(login_url="login")
def edit_exam(request, exam_id):
    """
    Teacher can edit an existing scheduled exam:
    title, start_time, end_time, duration, passing_marks, access_code.
    """
    try:
        exam_obj_id = ObjectId(exam_id)
    except Exception:
        messages.error(request, "Invalid exam ID.")
        return redirect("scheduled_exams")

    sub_query = get_teacher_subjects_query(request.user)
    user_sub_ids = [s["_id"] for s in subjects_collection.find(sub_query, {"_id": 1})]

    query = {"_id": exam_obj_id}
    if not is_admin_or_superuser(request.user):
        query["subject_id"] = {"$in": user_sub_ids}

    exam = exams_collection.find_one(query)
    if not exam:
        messages.error(request, "Exam not found or access denied.")
        return redirect("scheduled_exams")

    if request.method == "POST":
        title         = request.POST.get("title", "").strip()
        start_time    = request.POST.get("start_time", "").strip()
        end_time      = request.POST.get("end_time", "").strip()
        duration      = request.POST.get("duration_minutes", "").strip()
        passing_marks = request.POST.get("passing_marks", "").strip()
        access_code   = request.POST.get("access_code", "").strip()

        if not title:
            messages.error(request, "Exam title is required.")
        else:
            update_data = {
                "title":          title,
                "start_time":     start_time,
                "end_time":       end_time,
                "access_code":    access_code,
            }
            if duration.isdigit():
                update_data["duration_minutes"] = int(duration)
            if passing_marks.isdigit():
                update_data["passing_marks"] = int(passing_marks)

            exams_collection.update_one(
                {"_id": exam_obj_id},
                {"$set": update_data}
            )
            messages.success(request, f"Exam '{title}' updated successfully!")
            return redirect("scheduled_exams")

    exam["id"] = str(exam["_id"])
    return render(request, "edit_exam.html", {"exam": exam})