from django import forms
from .models import Subject, Syllabus, Question


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "code", "description"]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Database Management System",
                "required": True,
            }),
            "code": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., DBMS-101",
                "required": True,
            }),
            "description": forms.Textarea(attrs={
                "class": "form-input",
                "placeholder": "Enter subject details or syllabus outline...",
                "rows": 3,
            }),
        }


class SyllabusForm(forms.ModelForm):
    class Meta:
        model = Syllabus
        fields = ["subject", "unit_number", "title", "description"]

        widgets = {
            "subject": forms.Select(attrs={
                "class": "form-input",
                "required": True,
            }),
            "unit_number": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., 1",
                "min": 1,
                "required": True,
            }),
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Introduction to Relational Databases",
                "required": True,
            }),
            "description": forms.Textarea(attrs={
                "class": "form-input",
                "placeholder": "Key topics, concepts, or modules covered in this unit...",
                "rows": 3,
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["subject"].queryset = Subject.objects.filter(created_by=user)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            "subject", "unit", "question_type", "difficulty", "marks",
            "question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer"
        ]

        widgets = {
            "subject": forms.Select(attrs={"class": "form-input", "required": True}),
            "unit": forms.Select(attrs={"class": "form-input"}),
            "question_type": forms.Select(attrs={"class": "form-input", "id": "id_question_type"}),
            "difficulty": forms.Select(attrs={"class": "form-input"}),
            "marks": forms.NumberInput(attrs={"class": "form-input", "min": 1, "value": 1}),
            "question_text": forms.Textarea(attrs={
                "class": "form-input",
                "placeholder": "Type your question here...",
                "rows": 3,
                "required": True,
            }),
            "option_a": forms.TextInput(attrs={"class": "form-input", "placeholder": "Option A"}),
            "option_b": forms.TextInput(attrs={"class": "form-input", "placeholder": "Option B"}),
            "option_c": forms.TextInput(attrs={"class": "form-input", "placeholder": "Option C"}),
            "option_d": forms.TextInput(attrs={"class": "form-input", "placeholder": "Option D"}),
            "correct_answer": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., A (for MCQ) or True / False or sample answer",
                "required": True,
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["subject"].queryset = Subject.objects.filter(created_by=user)
            self.fields["unit"].queryset = Syllabus.objects.filter(subject__created_by=user)
