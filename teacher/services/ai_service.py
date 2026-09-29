"""
AI Question Generator Service

Enterprise Service Layer for generating structured questions.
Uses local Ollama (Qwen3) — 100% private, no data leaves your machine.
Falls back to a template engine if Ollama is not running.
"""

import json
import os
import re
import urllib.request
import urllib.error

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b"   # change to "qwen3-no-think:latest" if you prefer


def _ollama_chat(prompt: str, temperature: float = 0.3) -> str:
    """
    Sends a prompt to the local Ollama /api/generate endpoint.
    Returns the raw response text.
    Raises RuntimeError if Ollama is unreachable or returns an error.
    """
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 2048,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable: {e}")


def _parse_json_from_response(raw: str) -> dict | list:
    """
    Strips markdown fences (```json ... ```) and parses JSON.
    Raises ValueError if JSON can't be parsed.
    """
    # Remove thinking blocks if present (<think>...</think>)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = raw.rstrip("`").strip()
    return json.loads(raw)


class AIQuestionGeneratorService:
    def __init__(self):
        # No API key needed — everything is local via Ollama
        self._ollama_available = None  # lazy-check

    def _check_ollama(self) -> bool:
        """Returns True if Ollama is reachable."""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            self._ollama_available = True
        except Exception:
            self._ollama_available = False
        return self._ollama_available

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
        count = max(1, min(int(count), 20))  # Max 20 per batch

        if self._check_ollama():
            try:
                return self._generate_with_ollama(
                    subject_name, syllabus_topics, count,
                    question_type, difficulty, custom_prompt
                )
            except Exception as e:
                print(f"[AI Service Warning] Ollama failed ({e}), using fallback engine.")

        return self._generate_fallback_questions(
            subject_name, syllabus_topics, count, question_type, difficulty, custom_prompt
        )

    def _generate_with_ollama(
        self,
        subject_name: str,
        syllabus_topics: list,
        count: int,
        question_type: str,
        difficulty: str,
        custom_prompt: str,
    ) -> list:
        """Generates questions using local Ollama / Qwen3."""
        topics_text = "\n".join(syllabus_topics) if syllabus_topics else subject_name

        prompt = f"""You are an expert academic examiner. Generate exactly {count} examination questions for the subject: '{subject_name}'.

SYLLABUS CONTEXT / TOPICS:
{topics_text}

ADDITIONAL INSTRUCTIONS:
{custom_prompt or 'None'}

REQUIREMENTS:
- Question Type: {question_type} (MCQ, TRUE_FALSE, or DESCRIPTIVE)
- Difficulty Level: {difficulty} (EASY, MEDIUM, or HARD)
- For MCQ: Provide 4 distinct options (option_a to option_d), set marks=2, correct_answer = A/B/C/D.
- For True/False: option_a='True', option_b='False', marks=1, correct_answer='True' or 'False'.
- For Descriptive: options are empty strings, marks=5, provide a detailed sample solution in correct_answer.

OUTPUT FORMAT — return ONLY valid JSON, no explanation, no markdown:
{{
    "questions": [
        {{
            "question_text": "Question text here",
            "question_type": "{question_type}",
            "difficulty": "{difficulty}",
            "marks": 2,
            "option_a": "Option A",
            "option_b": "Option B",
            "option_c": "Option C",
            "option_d": "Option D",
            "correct_answer": "A"
        }}
    ]
}}"""

        raw = _ollama_chat(prompt, temperature=0.3)
        data = _parse_json_from_response(raw)
        if isinstance(data, dict):
            return data.get("questions", [])
        return data  # if model returned a list directly

    def _generate_fallback_questions(
        self,
        subject_name: str,
        syllabus_topics: list,
        count: int,
        question_type: str,
        difficulty: str,
        custom_prompt: str,
    ) -> list:
        """Template-based fallback when Ollama is offline."""
        topics = [t for t in syllabus_topics if len(t) > 3] if syllabus_topics else [subject_name]
        generated = []

        for i in range(count):
            topic = topics[i % len(topics)]
            clean_topic = re.sub(r"^[\-\*\s\d\.\)]+", "", topic).strip() or subject_name

            if question_type == "MCQ":
                q_doc = {
                    "question_text": f"Which of the following statements is true regarding {clean_topic} in {subject_name}?",
                    "question_type": "MCQ",
                    "difficulty": difficulty,
                    "marks": 2,
                    "option_a": f"It defines the primary mechanism for {clean_topic}.",
                    "option_b": f"It is unrelated to {subject_name}.",
                    "option_c": "It only applies to legacy systems.",
                    "option_d": "None of the above.",
                    "correct_answer": "A",
                }
            elif question_type == "TRUE_FALSE":
                q_doc = {
                    "question_text": f"True or False: {clean_topic} plays a fundamental role in {subject_name}.",
                    "question_type": "TRUE_FALSE",
                    "difficulty": difficulty,
                    "marks": 1,
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
                    "marks": 5,
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
        Analyses a student's exam results locally via Ollama.
        Returns weak/strong topics, study suggestions, and YouTube links.
        """
        if self._check_ollama():
            try:
                return self._analyze_with_ollama(
                    subject_name, wrong_questions, correct_questions, exam_title
                )
            except Exception as e:
                print(f"[AI Analytics Warning] Ollama failed ({e}), using fallback.")

        return self._analyze_fallback(subject_name, wrong_questions, correct_questions)

    def _analyze_with_ollama(
        self, subject_name, wrong_questions, correct_questions, exam_title
    ) -> dict:
        wrong_text = "\n".join(
            [f"- {q.get('question_text', '')} (Answered: '{q.get('student_answer', '')}')"
             for q in wrong_questions]
        ) or "None"
        correct_text = "\n".join(
            [f"- {q.get('question_text', '')} (Answered: '{q.get('student_answer', '')}')"
             for q in correct_questions]
        ) or "None"

        prompt = f"""You are an academic performance coach. A student completed the exam: "{exam_title}" in subject "{subject_name}".

QUESTIONS THE STUDENT GOT WRONG:
{wrong_text}

QUESTIONS THE STUDENT ANSWERED CORRECTLY:
{correct_text}

Analyse the student's performance and return ONLY valid JSON (no explanation, no markdown):
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
- study_suggestions: max 4, specific and actionable
- youtube_links: 3 to 5 links, one per weak topic, YouTube search URLs only"""

        raw = _ollama_chat(prompt, temperature=0.4)
        return json.loads(_parse_json_from_response(raw) if isinstance(_parse_json_from_response(raw), str) else json.dumps(_parse_json_from_response(raw)))

    def _analyze_fallback(self, subject_name, wrong_questions, correct_questions) -> dict:
        """Fallback when Ollama is offline."""
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
        Grades a descriptive answer locally via Ollama / Qwen3.
        Returns awarded_marks, feedback, key_points_covered, key_points_missing.
        """
        if not student_answer or not student_answer.strip():
            return {
                "awarded_marks": 0,
                "feedback": "No answer was provided for this question.",
                "key_points_covered": [],
                "key_points_missing": ["Full answer required"],
            }

        if self._check_ollama():
            try:
                return self._grade_with_ollama(
                    question_text, sample_answer, student_answer, max_marks
                )
            except Exception as e:
                print(f"[AI Grader Warning] Ollama grading failed ({e}), using keyword fallback.")

        return self._grade_fallback(question_text, sample_answer, student_answer, max_marks)

    def _grade_with_ollama(
        self,
        question_text: str,
        sample_answer: str,
        student_answer: str,
        max_marks: int,
    ) -> dict:
        """Grades a descriptive answer using local Qwen3 via Ollama."""
        prompt = f"""You are an academic examiner evaluating a student's descriptive answer.

QUESTION:
{question_text}

SAMPLE CORRECT ANSWER (Teacher's Reference):
{sample_answer}

STUDENT'S SUBMITTED ANSWER:
{student_answer}

MAXIMUM MARKS FOR THIS QUESTION: {max_marks}

Evaluate the student's answer based on:
1. Accuracy of key concepts
2. Completeness relative to the sample answer
3. Clarity of explanation

Return ONLY valid JSON (no explanation, no markdown):
{{
    "awarded_marks": <integer between 0 and {max_marks}>,
    "feedback": "<2-3 sentences of constructive student-friendly feedback>",
    "key_points_covered": ["<concept 1>", "<concept 2>"],
    "key_points_missing": ["<missing concept 1>", "<missing concept 2>"]
}}

Rules:
- awarded_marks must be an integer from 0 to {max_marks}
- feedback must be encouraging, specific, and constructive
- key_points_covered: max 4 concepts the student correctly addressed
- key_points_missing: max 4 important concepts the student missed
- If the answer is completely unrelated, awarded_marks = 0"""

        raw = _ollama_chat(prompt, temperature=0.2)
        data = _parse_json_from_response(raw)
        if isinstance(data, str):
            data = json.loads(data)
        data["awarded_marks"] = max(0, min(int(data.get("awarded_marks", 0)), max_marks))
        return data

    def _grade_fallback(
        self,
        question_text: str,
        sample_answer: str,
        student_answer: str,
        max_marks: int,
    ) -> dict:
        """Keyword-overlap fallback grader when Ollama is offline."""
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
