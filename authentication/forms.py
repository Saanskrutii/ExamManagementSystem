"""
Authentication Forms

WHY we use Django Forms:
- They handle input validation (is the email valid? is the password strong enough?)
- They protect against CSRF attacks automatically
- They integrate with Django's auth system (authenticate, create_user)
- They render HTML form fields for us

WHY we DON'T just use raw HTML forms:
- No built-in validation
- No CSRF protection
- We'd have to manually query the database
- More code, more bugs
"""

from django import forms
from django.contrib.auth import authenticate
from .models import CustomUser


class LoginForm(forms.Form):
    """
    Login form — NOT a ModelForm because we're not creating a user,
    we're just collecting credentials to verify against the database.
    """

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Enter your username",
            "autocomplete": "username",
            "id": "username",
        }),
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
            "id": "password",
        }),
    )

    def clean(self):
        """
        clean() runs after individual field validations pass.
        Here we check if the username + password combination is valid.

        WHY here and not in the view?
        - Keeps authentication logic inside the form (single responsibility)
        - The view just calls form.is_valid() — clean and simple
        """
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if username and password:
            # authenticate() checks credentials against the database
            # Returns the user object if valid, None if invalid
            user = authenticate(username=username, password=password)

            if user is None:
                raise forms.ValidationError("Invalid username or password.")

            if not user.is_active:
                raise forms.ValidationError("This account is deactivated.")

            # Store the authenticated user so the view can access it
            cleaned_data["user"] = user

        return cleaned_data


class SignupForm(forms.ModelForm):
    """
    Signup form — IS a ModelForm because we ARE creating a new user.

    ModelForm automatically generates form fields from the model.
    We only specify the fields we want on the signup page.
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Create a password",
            "autocomplete": "new-password",
            "id": "password",
        }),
    )

    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Confirm your password",
            "autocomplete": "new-password",
            "id": "confirm_password",
        }),
    )

    class Meta:
        model = CustomUser
        fields = ["username", "email", "role"]

        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Choose a username",
                "autocomplete": "username",
                "id": "username",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-input",
                "placeholder": "you@example.com",
                "autocomplete": "email",
                "id": "email",
            }),
            "role": forms.Select(attrs={
                "class": "form-input",
                "id": "role",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow TEACHER and STUDENT roles on signup
        # ADMIN accounts should only be created by superusers via admin panel
        self.fields["role"].choices = [
            (CustomUser.Role.TEACHER, "Teacher"),
            (CustomUser.Role.STUDENT, "Student"),
        ]

    def clean(self):
        """Validate that both passwords match."""
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data

    def save(self, commit=True):
        """
        Override save() to hash the password before storing.

        WHY: If we just did user.password = 'raw_password', it would store
        the plain text password. set_password() hashes it securely.
        """
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])

        if commit:
            user.save()

        return user
