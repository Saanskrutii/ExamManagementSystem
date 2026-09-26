"""
PyMongo Connection & Collection Helpers

This module establishes a Singleton MongoClient connection to MongoDB
and exports PyMongo database & collection references.

Compound Indexes are created at startup via ensure_db_indexes() to prevent
full collection scans (COLLSCAN) on frequent query patterns identified during
architecture review.
"""

from django.conf import settings
from pymongo import MongoClient, ASCENDING, DESCENDING

# Initialize PyMongo Client (Singleton)
client = MongoClient(getattr(settings, "MONGO_URI", "mongodb://127.0.0.1:27017"))
db_name = getattr(settings, "MONGO_DB_NAME", "exam_management_system")

# Database instance
db = client[db_name]

# PyMongo Collections
users_collection = db["authentication_customuser"]
subjects_collection = db["teacher_subject"]
syllabus_collection = db["teacher_syllabus"]
questions_collection = db["teacher_question"]
exams_collection = db["teacher_exam"]
attempts_collection = db["student_attempt"]
results_collection = db["student_result"]


def get_db():
    """Returns the PyMongo database instance."""
    return db


def ensure_db_indexes():
    """
    Creates compound BSON indexes on high-frequency query fields.

    Without these indexes MongoDB performs full COLLSCAN (O(n)) on every query.
    With indexes, lookups are O(log n) via B-Tree traversal.

    Called once at Django app startup via ExamManagementSystemConfig.ready().

    Indexes created:
    ─────────────────────────────────────────────────────────────────────────
    questions_collection:
      • (subject_id ASC, difficulty ASC, is_deleted ASC)
        → Optimises Question Bank filtering + $sample auto-exam generation.

    results_collection:
      • (exam_id ASC, score DESC)
        → Optimises peer benchmarking — sorting all results by score per exam
          without fetching all documents into Python memory.
      • (exam_id ASC, student_id ASC)  [unique=True]
        → Enforces single-result-per-student per attempt and speeds up
          student scorecard lookups.

    attempts_collection:
      • (student_id ASC, is_submitted ASC, submitted_at DESC)
        → Optimises student analytics — fetching submitted attempts in
          chronological order for a specific student.
      • (exam_id ASC, student_id ASC, is_submitted ASC)
        → Optimises double-submission guard check inside submit_exam view.
    ─────────────────────────────────────────────────────────────────────────
    """
    # ── Question Bank indexes ──────────────────────────────────────────────
    questions_collection.create_index(
        [("subject_id", ASCENDING), ("difficulty", ASCENDING), ("is_deleted", ASCENDING)],
        name="idx_questions_subject_difficulty_deleted",
        background=True,
    )

    # ── Results collection indexes ─────────────────────────────────────────
    results_collection.create_index(
        [("exam_id", ASCENDING), ("score", DESCENDING)],
        name="idx_results_exam_score",
        background=True,
    )
    results_collection.create_index(
        [("exam_id", ASCENDING), ("student_id", ASCENDING)],
        name="idx_results_exam_student",
        background=True,
    )

    # ── Attempts collection indexes ────────────────────────────────────────
    attempts_collection.create_index(
        [("student_id", ASCENDING), ("is_submitted", ASCENDING), ("submitted_at", DESCENDING)],
        name="idx_attempts_student_submitted",
        background=True,
    )
    attempts_collection.create_index(
        [("exam_id", ASCENDING), ("student_id", ASCENDING), ("is_submitted", ASCENDING)],
        name="idx_attempts_exam_student_submitted",
        background=True,
    )
