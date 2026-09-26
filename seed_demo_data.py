import os
import sys
import django
from datetime import datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from bson import ObjectId
from config.db import (
    users_collection,
    subjects_collection,
    syllabus_collection,
    questions_collection,
    exams_collection,
    attempts_collection,
    results_collection,
)

User = get_user_model()

def seed_data():
    print("🌱 Starting Demo Data Seeding for Exam Management System...")

    # 1. Clean existing demo data (preserving system state)
    print("🧹 Cleaning old sample records...")
    subjects_collection.delete_many({})
    syllabus_collection.delete_many({})
    questions_collection.delete_many({})
    exams_collection.delete_many({})
    attempts_collection.delete_many({})
    results_collection.delete_many({})

    # 2. Ensure Users Exist (Admin, Teacher, Students)
    print("👤 Setting up Demo Users...")

    def create_or_update_user(username, email, role, password, first_name, last_name):
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=role,
                first_name=first_name,
                last_name=last_name,
            )
        else:
            user.set_password(password)
            user.role = role
            user.first_name = first_name
            user.last_name = last_name
            user.save()
        return user

    admin_user = create_or_update_user("admin", "admin@exam.com", "ADMIN", "admin123", "System", "Admin")
    teacher_user = create_or_update_user("teacher", "teacher@exam.com", "TEACHER", "teacher123", "Sanskruti", "Gosavi")
    student1_user = create_or_update_user("student", "student@exam.com", "STUDENT", "student123", "Rahul", "Sharma")
    student2_user = create_or_update_user("student2", "student2@exam.com", "STUDENT", "student123", "Priya", "Patel")

    teacher_id = teacher_user.id
    student1_id = student1_user.id
    student2_id = student2_user.id

    now = datetime.utcnow()

    # 3. Create Subjects
    print("📚 Creating Subjects...")
    sub_py_id = ObjectId()
    sub_db_id = ObjectId()
    sub_ds_id = ObjectId()

    subjects_data = [
        {
            "_id": sub_py_id,
            "name": "Python Programming",
            "code": "CS-101",
            "description": "Core Python programming, data structures, OOPs, and web development.",
            "created_by_id": teacher_id,
            "created_at": now - timedelta(days=10),
            "updated_at": now - timedelta(days=10),
        },
        {
            "_id": sub_db_id,
            "name": "Database Management Systems",
            "code": "CS-102",
            "description": "Relational databases, SQL queries, MongoDB document stores, and indexing.",
            "created_by_id": teacher_id,
            "created_at": now - timedelta(days=8),
            "updated_at": now - timedelta(days=8),
        },
        {
            "_id": sub_ds_id,
            "name": "Data Structures & Algorithms",
            "code": "CS-103",
            "description": "Arrays, linked lists, stacks, queues, trees, graphs, sorting, and searching.",
            "created_by_id": teacher_id,
            "created_at": now - timedelta(days=6),
            "updated_at": now - timedelta(days=6),
        },
    ]
    subjects_collection.insert_many(subjects_data)

    # 4. Create Syllabus Units
    print("📖 Creating Syllabus Units...")
    syllabus_data = [
        # Python Syllabus
        {"_id": ObjectId(), "subject_id": sub_py_id, "unit_number": 1, "title": "Unit 1: Python Basics & Control Structures", "description": "Variables, data types, if-else conditionals, for loops, while loops, and range functions.", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "subject_id": sub_py_id, "unit_number": 2, "title": "Unit 2: Functions, Modules & Scopes", "description": "Defining functions, lambda functions, positional/keyword arguments, imports, and scope resolution.", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "subject_id": sub_py_id, "unit_number": 3, "title": "Unit 3: Object-Oriented Programming (OOP)", "description": "Classes, objects, inheritance, polymorphism, encapsulation, and magic methods.", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "subject_id": sub_py_id, "unit_number": 4, "title": "Unit 4: Exception Handling & File I/O", "description": "Try-except-finally blocks, custom exceptions, reading/writing text & CSV files.", "created_at": now, "updated_at": now},
        
        # DBMS Syllabus
        {"_id": ObjectId(), "subject_id": sub_db_id, "unit_number": 1, "title": "Unit 1: Introduction to DBMS & Relational Model", "description": "ER diagrams, relational schema, primary keys, foreign keys, and normal forms.", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "subject_id": sub_db_id, "unit_number": 2, "title": "Unit 2: SQL & Complex Queries", "description": "SELECT, JOINs, GROUP BY, HAVING, subqueries, views, and aggregate functions.", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "subject_id": sub_db_id, "unit_number": 3, "title": "Unit 3: NoSQL & MongoDB Architecture", "description": "Document databases, JSON/BSON formats, PyMongo driver, collections, and CRUD operations.", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "subject_id": sub_db_id, "unit_number": 4, "title": "Unit 4: Indexing & Aggregation Pipelines", "description": "Single-field & compound indexes, $match, $group, $sort, $lookup, and $sample stages.", "created_at": now, "updated_at": now},
    ]
    syllabus_collection.insert_many(syllabus_data)

    # 5. Create Rich Question Bank
    print("❓ Creating Rich Question Bank...")
    q_py_1 = ObjectId()
    q_py_2 = ObjectId()
    q_py_3 = ObjectId()
    q_py_4 = ObjectId()
    q_py_5 = ObjectId()
    q_py_6 = ObjectId()

    q_db_1 = ObjectId()
    q_db_2 = ObjectId()
    q_db_3 = ObjectId()

    questions_data = [
        # Python Questions
        {
            "_id": q_py_1,
            "subject_id": sub_py_id,
            "unit_id": None,
            "question_type": "MCQ",
            "difficulty": "EASY",
            "marks": 2,
            "question_text": "What is the output of print(2 ** 3) in Python?",
            "option_a": "6", "option_b": "8", "option_c": "9", "option_d": "5",
            "correct_answer": "B",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_py_2,
            "subject_id": sub_py_id,
            "unit_id": None,
            "question_type": "MCQ",
            "difficulty": "MEDIUM",
            "marks": 2,
            "question_text": "Which of the following data structures in Python is immutable?",
            "option_a": "List", "option_b": "Dictionary", "option_c": "Tuple", "option_d": "Set",
            "correct_answer": "C",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_py_3,
            "subject_id": sub_py_id,
            "unit_id": None,
            "question_type": "TRUE_FALSE",
            "difficulty": "EASY",
            "marks": 1,
            "question_text": "True or False: Python uses dynamic typing, meaning variable types are determined at runtime.",
            "option_a": "True", "option_b": "False", "option_c": "", "option_d": "",
            "correct_answer": "True",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_py_4,
            "subject_id": sub_py_id,
            "unit_id": None,
            "question_type": "MCQ",
            "difficulty": "HARD",
            "marks": 5,
            "question_text": "In Python, which built-in function returns a shallow copy of an object when combined with slicing?",
            "option_a": "list.copy()", "option_b": "list[:]", "option_c": "copy.deepcopy()", "option_d": "Both A and B",
            "correct_answer": "D",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_py_5,
            "subject_id": sub_py_id,
            "unit_id": None,
            "question_type": "DESCRIPTIVE",
            "difficulty": "MEDIUM",
            "marks": 5,
            "question_text": "Explain the difference between list append() and extend() methods in Python with code snippets.",
            "option_a": "", "option_b": "", "option_c": "", "option_d": "",
            "correct_answer": "Sample Solution: append() adds its argument as a single element to the end of a list, whereas extend() iterates over its argument adding each element to the list.",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_py_6,
            "subject_id": sub_py_id,
            "unit_id": None,
            "question_type": "TRUE_FALSE",
            "difficulty": "MEDIUM",
            "marks": 1,
            "question_text": "True or False: The 'finally' block in Python exception handling executes regardless of whether an exception is raised or caught.",
            "option_a": "True", "option_b": "False", "option_c": "", "option_d": "",
            "correct_answer": "True",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },

        # DBMS Questions
        {
            "_id": q_db_1,
            "subject_id": sub_db_id,
            "unit_id": None,
            "question_type": "MCQ",
            "difficulty": "EASY",
            "marks": 2,
            "question_text": "In MongoDB, which format is used to store document records on disk?",
            "option_a": "JSON", "option_b": "BSON", "option_c": "XML", "option_d": "CSV",
            "correct_answer": "B",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_db_2,
            "subject_id": sub_db_id,
            "unit_id": None,
            "question_type": "MCQ",
            "difficulty": "MEDIUM",
            "marks": 2,
            "question_text": "Which aggregation stage in MongoDB is used to randomly select documents from a collection?",
            "option_a": "$match", "option_b": "$sample", "option_c": "$group", "option_d": "$lookup",
            "correct_answer": "B",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
        {
            "_id": q_db_3,
            "subject_id": sub_db_id,
            "unit_id": None,
            "question_type": "TRUE_FALSE",
            "difficulty": "EASY",
            "marks": 1,
            "question_text": "True or False: MongoDB supports ACID transactions across multiple documents.",
            "option_a": "True", "option_b": "False", "option_c": "", "option_d": "",
            "correct_answer": "True",
            "created_by_id": teacher_id, "created_at": now, "updated_at": now,
        },
    ]
    questions_collection.insert_many(questions_data)

    # 6. Create Scheduled & Live Exams
    print("📝 Creating Scheduled & Live Exams...")
    exam_live_id = ObjectId()
    exam_sched_id = ObjectId()
    exam_comp_id = ObjectId()

    # Dates in IST string format "YYYY-MM-DDTHH:MM"
    # To ensure LIVE status: start = yesterday, end = tomorrow
    start_live = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    end_live = (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")

    start_sched = (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    end_sched = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")

    start_comp = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
    end_comp = (now - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M")

    exams_data = [
        {
            "_id": exam_live_id,
            "title": "Python Midterm Assessment 2026",
            "subject_id": sub_py_id,
            "created_by_id": teacher_id,
            "duration_minutes": 45,
            "total_marks": 16,
            "passing_marks": 8,
            "access_code": "PY2026",
            "start_time": start_live,
            "end_time": end_live,
            "question_ids": [q_py_1, q_py_2, q_py_3, q_py_4, q_py_5, q_py_6],
            "assembly_mode": "MANUAL",
            "status": "LIVE",
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=2),
        },
        {
            "_id": exam_sched_id,
            "title": "Database Systems Final Examination",
            "subject_id": sub_db_id,
            "created_by_id": teacher_id,
            "duration_minutes": 60,
            "total_marks": 20,
            "passing_marks": 10,
            "access_code": "DB2026",
            "start_time": start_sched,
            "end_time": end_sched,
            "question_ids": [q_db_1, q_db_2, q_db_3],
            "assembly_mode": "AUTO",
            "status": "SCHEDULED",
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(days=1),
        },
        {
            "_id": exam_comp_id,
            "title": "Python Quiz 1 - Fundamentals",
            "subject_id": sub_py_id,
            "created_by_id": teacher_id,
            "duration_minutes": 30,
            "total_marks": 10,
            "passing_marks": 5,
            "access_code": "QUIZ101",
            "start_time": start_comp,
            "end_time": end_comp,
            "question_ids": [q_py_1, q_py_2, q_py_3],
            "assembly_mode": "MANUAL",
            "status": "COMPLETED",
            "created_at": now - timedelta(days=8),
            "updated_at": now - timedelta(days=8),
        },
    ]
    exams_collection.insert_many(exams_data)

    # 7. Create Student Attempts & Results (For Rich Analytics!)
    print("📊 Creating Student Attempts & Results for Analytics...")
    att1_id = ObjectId()
    att2_id = ObjectId()

    attempts_data = [
        {
            "_id": att1_id,
            "student_id": student1_id,
            "exam_id": exam_comp_id,
            "responses": {
                str(q_py_1): "B",
                str(q_py_2): "C",
                str(q_py_3): "True",
            },
            "started_at": now - timedelta(days=6, hours=2),
            "submitted_at": now - timedelta(days=6, hours=1),
            "is_submitted": True,
        },
        {
            "_id": att2_id,
            "student_id": student2_id,
            "exam_id": exam_comp_id,
            "responses": {
                str(q_py_1): "A",  # Wrong
                str(q_py_2): "C",  # Correct
                str(q_py_3): "True", # Correct
            },
            "started_at": now - timedelta(days=6, hours=1),
            "submitted_at": now - timedelta(days=6, minutes=30),
            "is_submitted": True,
        },
    ]
    attempts_collection.insert_many(attempts_data)

    results_data = [
        {
            "_id": ObjectId(),
            "student_id": student1_id,
            "exam_id": exam_comp_id,
            "attempt_id": att1_id,
            "score": 5,
            "total_marks": 5,
            "passing_marks": 3,
            "percentage": 100.0,
            "status": "PASSED",
            "evaluated_at": now - timedelta(days=6, hours=1),
        },
        {
            "_id": ObjectId(),
            "student_id": student2_id,
            "exam_id": exam_comp_id,
            "attempt_id": att2_id,
            "score": 3,
            "total_marks": 5,
            "passing_marks": 3,
            "percentage": 60.0,
            "status": "PASSED",
            "evaluated_at": now - timedelta(days=6, minutes=30),
        },
    ]
    results_collection.insert_many(results_data)

    print("\n✅ SEEDING COMPLETE! Your database is now loaded with rich demo data.")
    print("----------------------------------------------------------------------")
    print("🔑 DEMO LOGIN CREDENTIALS:")
    print("   • Teacher Account :  username: teacher   | password: teacher123")
    print("   • Student Account :  username: student   | password: student123")
    print("   • Admin Account   :  username: admin     | password: admin123")
    print("   • LIVE Exam Access Code :  PY2026")
    print("----------------------------------------------------------------------\n")

if __name__ == "__main__":
    seed_data()
