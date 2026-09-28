"""
AI Question Generator Service

Enterprise Service Layer for generating structured questions.
Supports Google Gemini API with fallback synthesis engine.
"""

import json
import os
import re
from django.conf import settings


class AIQuestionGeneratorService:
    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", None))

    def generate_questions(
        self,
        subject_name: str,
        syllabus_topics: list,
        count: int = 5,
        question_type: str = "MCQ",
        difficulty: str = "MEDIUM",
        custom_prompt: str = "",
    ) -> list:
        """
        Orchestrates AI question generation.
        Returns a list of clean question dicts.
        """
        count = max(1, min(int(count), 20))  # Enterprise limit: max 20 per batch

        if self.api_key:
            try:
                return self._generate_with_gemini(
                    subject_name, syllabus_topics, count, question_type, difficulty, custom_prompt
                )
            except Exception as e:
                # Log error and fall back cleanly
                print(f"[AI Service Warning] Gemini API failed ({e}), using Context Synthesizer Engine.")

        return self._generate_fallback_questions(
            subject_name, syllabus_topics, count, question_type, difficulty, custom_prompt
        )

    def _generate_with_gemini(
        self,
        subject_name: str,
        syllabus_topics: list,
        count: int,
        question_type: str,
        difficulty: str,
        custom_prompt: str,
    ) -> list:
        """
        Generates questions using official google-genai SDK.
        """
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        topics_text = "\n".join(syllabus_topics) if syllabus_topics else subject_name

        prompt = f"""
You are an expert academic examiner. Generate exactly {count} examination questions for the subject: '{subject_name}'.

SYLLABUS CONTEXT / TOPICS:
{topics_text}

ADDITIONAL INSTRUCTIONS:
{custom_prompt or 'None'}

REQUIREMENTS:
- Question Type: {question_type} (MCQ, TRUE_FALSE, or DESCRIPTIVE)
- Difficulty Level: {difficulty} (EASY, MEDIUM, or HARD)
- For MCQ: Provide 4 distinct options (option_a, option_b, option_c, option_d), set marks=2, and specify correct_answer as A, B, C, or D.
- For True/False: Set option_a='True', option_b='False', set marks=1, and correct_answer as 'True' or 'False'.
- For Descriptive: Set options as empty strings, set marks=5, and provide a detailed sample solution in correct_answer.

OUTPUT FORMAT:
Return ONLY valid JSON matching this structure:
{
    "questions": [
        {
            "question_text": "Question text here",
            "question_type": "{question_type}",
            "difficulty": "{difficulty}",
            "marks": 2,
            "option_a": "Option A text",
            "option_b": "Option B text",
            "option_c": "Option C text",
            "option_d": "Option D text",
            "correct_answer": "A"
        }
    ]
}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )

        raw_json = response.text.strip()
        data = json.loads(raw_json)
        return data.get("questions", [])

    def _generate_fallback_questions(
        self,
        subject_name: str,
        syllabus_topics: list,
        count: int,
        question_type: str,
        difficulty: str,
        custom_prompt: str,
    ) -> list:
        """
        Context-aware synthesis fallback engine.
        Ensures the application functions reliably even offline or without API key.
        """
        topics = [t for t in syllabus_topics if len(t) > 3] if syllabus_topics else [subject_name]
        generated = []

        for i in range(count):
            topic = topics[i % len(topics)]
            # Clean bullet symbols from topic
            clean_topic = re.sub(r"^[\bullet\-\*\s\d\.\)]+", "", topic).strip()
            if not clean_topic:
                clean_topic = subject_name

            if question_type == "MCQ":
                q_doc = {
                    "question_text": f"Which of the following statements is true regarding {clean_topic} in {subject_name}?",
                    "question_type": "MCQ",
                    "difficulty": difficulty,
                    "marks": 2,  # MCQs are strictly 2 marks!
                    "option_a": f"It defines the primary mechanism for {clean_topic}.",
                    "option_b": f"It is unrelated to {subject_name}.",
                    "option_c": f"It only applies to legacy systems.",
                    "option_d": f"None of the above.",
                    "correct_answer": "A",
                }
            elif question_type == "TRUE_FALSE":
                q_doc = {
                    "question_text": f"True or False: {clean_topic} plays a fundamental role in {subject_name}.",
                    "question_type": "TRUE_FALSE",
                    "difficulty": difficulty,
                    "marks": 1,  # True/False is strictly 1 mark!
                    "option_a": "True",
                    "option_b": "False",
                    "option_c": "",
                    "option_d": "",
                    "correct_answer": "True",
                }
            else:
                q_doc = {
                    "question_text": f"Explain in detail the key concepts and applications of {clean_topic} within {subject_name}.",
                    "question_type": "DESCRIPTIVE",
                    "difficulty": difficulty,
                    "marks": 5,  # Descriptive is 5 marks!
                    "option_a": "",
                    "option_b": "",
                    "option_c": "",
                    "option_d": "",
                    "correct_answer": f"Sample Solution: Key principles of {clean_topic} involve structural components, workflow rules, and optimization guidelines in {subject_name}.",
                }

            generated.append(q_doc)

        return generated

    # ──────────────────────────────────────────────────────────────────────────
    # Student Performance Analysis
    # ──────────────────────────────────────────────────────────────────────────

    def analyze_student_performance(
        self,
        subject_name: str,
        wrong_questions: list,
        correct_questions: list,
        exam_title: str = "",
    ) -> dict:
        """
        Uses Gemini to analyze student's wrong/correct answers and return:
        - weak_topics: list of topic areas they struggle with
        - strong_topics: list of areas they're doing well in
        - study_suggestions: list of actionable tips
        - youtube_links: list of {title, url} dicts with YouTube search links
        """
        if self.api_key:
            try:
                return self._analyze_with_gemini(
                    subject_name, wrong_questions, correct_questions, exam_title
                )
            except Exception as e:
                print(f"[AI Analytics Warning] Gemini failed ({e}), using fallback.")

        return self._analyze_fallback(subject_name, wrong_questions, correct_questions)

    def _analyze_with_gemini(
        self, subject_name, wrong_questions, correct_questions, exam_title
    ) -> dict:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        wrong_text = "\n".join(
            [f"- {q.get('question_text', '')} (Student Answered: '{q.get('student_answer', '')}')" for q in wrong_questions]
        ) or "None"
        correct_text = "\n".join(
            [f"- {q.get('question_text', '')} (Student Answered: '{q.get('student_answer', '')}')" for q in correct_questions]
        ) or "None"

        prompt = f"""
You are an academic performance coach. A student just completed the exam: "{exam_title}" in subject "{subject_name}".

QUESTIONS THE STUDENT GOT WRONG:
{wrong_text}

QUESTIONS THE STUDENT ANSWERED CORRECTLY:
{correct_text}

Analyze the student's performance and return a JSON with exactly this structure:
{{
    "weak_topics": ["topic1", "topic2", "topic3"],
    "strong_topics": ["topic1", "topic2"],
    "study_suggestions": [
        "Actionable tip 1",
        "Actionable tip 2",
        "Actionable tip 3"
    ],
    "youtube_links": [
        {{
            "title": "Descriptive video title for topic",
            "url": "https://www.youtube.com/results?search_query=relevant+search+terms"
        }}
    ]
}}

Rules:
- weak_topics: max 5, inferred from wrong questions
- strong_topics: max 3, inferred from correct questions
- study_suggestions: max 4, specific and actionable for this student
- youtube_links: 3 to 5 links, one per weak topic, YouTube search URLs only
- Keep all text concise and student-friendly
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        return json.loads(raw)

    def _analyze_fallback(self, subject_name, wrong_questions, correct_questions) -> dict:
        """Fallback when Gemini is unavailable."""
        import urllib.parse
        weak = [f"{subject_name} fundamentals"] if wrong_questions else []
        strong = [f"{subject_name} concepts"] if correct_questions else []
        query = urllib.parse.quote(f"{subject_name} exam concepts explained")
        return {
            "weak_topics": weak,
            "strong_topics": strong,
            "study_suggestions": [
                f"Review the core concepts of {subject_name}.",
                "Practice more questions on the topics you missed.",
                "Re-read your syllabus notes on weak areas.",
            ],
            "youtube_links": [
                {
                    "title": f"{subject_name} – Full Concept Review",
                    "url": f"https://www.youtube.com/results?search_query={query}",
                }
            ],
        }

    # ──────────────────────────────────────────────────────────────────────────
    # AI Descriptive Answer Grader
    # ──────────────────────────────────────────────────────────────────────────

    def grade_descriptive_answer(
        self,
        question_text: str,
        sample_answer: str,
        student_answer: str,
        max_marks: int = 5,
    ) -> dict:
        """
        Uses Gemini AI to evaluate a student's descriptive answer against the
        question and the teacher-provided sample answer.

        Returns a dict with:
          - awarded_marks  (int):   0 to max_marks
          - feedback       (str):   Constructive 2-3 sentence feedback for the student
          - key_points_covered (list[str]): Key concepts the student addressed correctly
          - key_points_missing (list[str]): Concepts missing from the student's answer
        """
        if not student_answer or not student_answer.strip():
            return {
                "awarded_marks": 0,
                "feedback": "No answer was provided for this question.",
                "key_points_covered": [],
                "key_points_missing": ["Full answer required"],
            }

        if self.api_key:
            try:
                return self._grade_with_gemini(
                    question_text, sample_answer, student_answer, max_marks
                )
            except Exception as e:
                print(f"[AI Grader Warning] Gemini grading failed ({e}), using keyword fallback.")

        return self._grade_fallback(question_text, sample_answer, student_answer, max_marks)

    def _grade_with_gemini(
        self,
        question_text: str,
        sample_answer: str,
        student_answer: str,
        max_marks: int,
    ) -> dict:
        """Grades a descriptive answer using Gemini 2.5 Flash."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        prompt = f"""
You are an academic examiner evaluating a student's descriptive answer.

QUESTION:
{question_text}

SAMPLE CORRECT ANSWER (Teacher's Reference):
{sample_answer}

STUDENT'S SUBMITTED ANSWER:
{student_answer}

MAXIMUM MARKS FOR THIS QUESTION: {max_marks}

Evaluate the student's answer fairly based on:
1. Accuracy of key concepts
2. Completeness relative to the sample answer
3. Clarity of explanation

Return ONLY valid JSON matching this exact structure:
{{
    "awarded_marks": <integer between 0 and {max_marks}>,
    "feedback": "<2-3 sentences of constructive student-friendly feedback>",
    "key_points_covered": ["<concept 1>", "<concept 2>"],
    "key_points_missing": ["<missing concept 1>", "<missing concept 2>"]
}}

Rules:
- awarded_marks must be an integer from 0 to {max_marks}
- feedback must be encouraging, specific, and constructive
- key_points_covered: list concepts the student correctly addressed (max 4)
- key_points_missing: list important concepts the student did not address (max 4)
- If the student's answer is completely unrelated, awarded_marks = 0
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        data = json.loads(raw)

        # Safety clamp on marks
        data["awarded_marks"] = max(0, min(int(data.get("awarded_marks", 0)), max_marks))
        return data

    def _grade_fallback(
        self,
        question_text: str,
        sample_answer: str,
        student_answer: str,
        max_marks: int,
    ) -> dict:
        """
        Keyword-overlap fallback grader when Gemini API is unavailable.
        Tokenises sample and student answers, computes Jaccard similarity,
        and awards proportional marks.
        """
        def tokenise(text):
            return set(re.sub(r"[^\w\s]", "", text.lower()).split())

        sample_tokens  = tokenise(sample_answer)
        student_tokens = tokenise(student_answer)

        if not sample_tokens:
            return {
                "awarded_marks": 0,
                "feedback": "No sample answer available to grade against.",
                "key_points_covered": [],
                "key_points_missing": [],
            }

        overlap = len(sample_tokens & student_tokens)
        jaccard = overlap / len(sample_tokens | student_tokens) if (sample_tokens | student_tokens) else 0

        # Scale to marks with a generous curve
        raw_score = jaccard * max_marks * 1.5
        awarded   = max(0, min(round(raw_score), max_marks))

        covered  = list(sample_tokens & student_tokens)[:4]
        missing  = list(sample_tokens - student_tokens)[:4]

        if awarded == max_marks:
            feedback = "Excellent answer! You have covered all key concepts clearly."
        elif awarded >= max_marks * 0.6:
            feedback = "Good attempt. You covered several key concepts but could expand on some areas."
        elif awarded >= max_marks * 0.3:
            feedback = "Partial credit awarded. Review the sample answer to strengthen your response."
        else:
            feedback = "Your answer needs significant improvement. Please revisit the topic."

        return {
            "awarded_marks": awarded,
            "feedback": feedback,
            "key_points_covered": covered,
            "key_points_missing": missing,
        }
