"""
Authentication Views

Each view follows the same pattern:
    GET  → Show the form (empty)
    POST → Process the form (validate → act → redirect)

WHY this pattern?
- GET requests should never modify data (HTTP standard)
- POST requests carry form data securely in the request body
- After a successful POST, we redirect (POST-Redirect-GET pattern)
  to prevent duplicate form submissions on browser refresh
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .forms import LoginForm, SignupForm
from .models import CustomUser


def home(request):
    """Landing page — public, no login required."""
    return render(request, "home.html")


def login_view(request):
    """
    Login view.

    GET:  Show empty login form
    POST: Validate credentials → log user in → redirect by role

    WHY we import as 'auth_login':
    - Django's login function is called 'login'
    - Our view is also called 'login_view'
    - We rename the import to avoid name collision
    """
    # If user is already logged in, send them to their dashboard
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        form = LoginForm(request.POST)

        if form.is_valid():
            user = form.cleaned_data["user"]

            # auth_login() does two things:
            # 1. Creates a session in the database
            # 2. Sets a session cookie in the user's browser
            # From this point, Django knows who this user is on every request
            auth_login(request, user)

            messages.success(request, f"Welcome back, {user.username}!")

            return redirect_by_role(user)
    else:
        form = LoginForm()

    return render(request, "login.html", {"form": form})


def signup_view(request):
    """
    Signup view.

    GET:  Show empty signup form
    POST: Validate data → create user → log them in → redirect

    WHY we log the user in immediately after signup:
    - Better user experience — no need to sign up then sign in again
    - Standard practice in modern web apps
    """
    # If user is already logged in, send them to their dashboard
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        form = SignupForm(request.POST)

        if form.is_valid():
            user = form.save()

            # Log the new user in immediately
            auth_login(request, user)

            messages.success(request, f"Account created! Welcome, {user.username}!")

            return redirect_by_role(user)
    else:
        form = SignupForm()

    return render(request, "signup.html", {"form": form})


@login_required(login_url="login")
def logout_view(request):
    """
    Logout view.

    WHY @login_required:
    - Only logged-in users can log out (obvious, but prevents errors)

    WHY login_url='login':
    - If someone who isn't logged in hits /logout/, redirect them to login page

    WHY we use POST for logout (in the template):
    - GET requests should never modify state
    - Logging out modifies state (destroys the session)
    - A GET logout is a security risk (CSRF: someone could embed
      <img src="/logout/"> and log users out without their knowledge)
    """
    auth_logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


def redirect_by_role(user):
    """
    Redirect user to the appropriate dashboard based on their role.

    WHY a separate function:
    - Used by both login_view and signup_view
    - Single place to update if we add new roles
    - Clean, readable code
    """
    if user.role == CustomUser.Role.TEACHER:
        return redirect("teacher_dashboard")
    elif user.role == CustomUser.Role.STUDENT:
        return redirect("student_dashboard")
    elif user.role == CustomUser.Role.ADMIN:
        return redirect("admin:index")
    else:
        return redirect("home")
