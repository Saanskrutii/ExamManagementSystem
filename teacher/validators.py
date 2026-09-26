"""
Input Sanitization & Tenant Security Validators

Enforces:
1. Object-Level Access Control (Tenant Isolation)
2. NoSQL / Input Injection Prevention
"""

from bson import ObjectId
from config.db import subjects_collection, syllabus_collection
from django.contrib.auth import get_user_model

User = get_user_model()


def get_user_id_variants(user_id):
    """
    Returns all possible type variants for a user_id [ObjectId, str]
    to ensure PyMongo $in / $or queries never fail due to BSON vs String type mismatches.
    """
    variants = [user_id]
    if isinstance(user_id, str):
        if len(user_id) == 24:
            try:
                variants.append(ObjectId(user_id))
            except Exception:
                pass
    elif isinstance(user_id, ObjectId):
        variants.append(str(user_id))
    return list(set(variants))


def validate_teacher_subject_access(subject_id_str, user_id):
    """
    Validates that the subject exists AND belongs to or is co-taught by the logged-in teacher.
    Bypasses ownership check for ADMIN users or superusers.
    Returns (is_valid: bool, subject_doc: dict, error_message: str)
    """
    if not subject_id_str:
        return False, None, "Subject ID is required."

    try:
        obj_id = ObjectId(subject_id_str)
    except Exception:
        return False, None, "Invalid Subject ID format."

    user_obj = User.objects.filter(id=user_id).first()
    is_admin = user_obj and (user_obj.role == "ADMIN" or user_obj.is_superuser)

    # Direct tenant check in MongoDB (bypass for ADMIN)
    query = {"_id": obj_id, "is_deleted": {"$ne": True}}
    if not is_admin:
        variants = get_user_id_variants(user_id)
        query["$or"] = [
            {"created_by_id": {"$in": variants}},
            {"co_teachers": {"$in": variants}}
        ]

    subject_doc = subjects_collection.find_one(query)

    if not subject_doc:
        return False, None, "Subject not found or access denied."

    return True, subject_doc, None


def validate_teacher_unit_access(unit_id_str, user_id):
    """
    Validates that the syllabus unit exists AND belongs to a subject owned/co-taught by the teacher.
    Bypasses ownership check for ADMIN users or superusers.
    """
    if not unit_id_str:
        return True, None, None  # Unit is optional

    try:
        obj_id = ObjectId(unit_id_str)
    except Exception:
        return False, None, "Invalid Unit ID format."

    unit_doc = syllabus_collection.find_one({"_id": obj_id})
    if not unit_doc:
        return False, None, "Syllabus Unit not found."

    user_obj = User.objects.filter(id=user_id).first()
    is_admin = user_obj and (user_obj.role == "ADMIN" or user_obj.is_superuser)

    # Check parent subject ownership or co-teacher access (bypass for ADMIN)
    query = {"_id": unit_doc["subject_id"], "is_deleted": {"$ne": True}}
    if not is_admin:
        variants = get_user_id_variants(user_id)
        query["$or"] = [
            {"created_by_id": {"$in": variants}},
            {"co_teachers": {"$in": variants}}
        ]

    sub_doc = subjects_collection.find_one(query)

    if not sub_doc:
        return False, None, "Access denied for this Syllabus Unit."

    return True, unit_doc, None


def sanitize_input_string(val, max_length=500):
    """
    Sanitizes user input strings to prevent prompt/script injection.
    """
    if not val:
        return ""
    cleaned = str(val).strip()
    # Remove null bytes or control characters
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32 or ch in "\n\r\t")
    return cleaned[:max_length]

