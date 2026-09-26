"""
Custom Django View Decorators for Tenant Validation & Access Security

Enforces:
1. Object-Level Access Control (Tenant Isolation between teachers/co-teachers)
2. Prevention of Unauthorized Access and Injection vulnerabilities
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from teacher.validators import validate_teacher_subject_access, validate_teacher_unit_access


def require_subject_access(param_name="subject"):
    """
    Django View Decorator to enforce tenant-level subject access control.
    
    Inspects:
    1. View kwargs (e.g., subject_id or subject in URL route)
    2. GET parameters (e.g. ?subject=<id> or ?subject_id=<id>)
    3. POST payload (e.g. subject_id)
    
    If valid, attaches validated `subject_doc` to `request.subject_doc`.
    If unauthorized or invalid, redirects to teacher subjects with an error alert,
    or returns an HTTP 403 JsonResponse for AJAX requests.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            
            sub_id = (
                kwargs.get("subject_id")
                or kwargs.get("subject")
                or request.GET.get("subject_id")
                or request.GET.get("subject")
                or request.POST.get("subject_id")
                or request.POST.get(param_name)
            )
            
            if sub_id:
                is_valid, subject_doc, err_msg = validate_teacher_subject_access(sub_id, request.user.id)
                if not is_valid:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type == "application/json":
                        return JsonResponse({"status": "error", "message": err_msg or "Access denied to subject."}, status=403)
                    messages.error(request, err_msg or "Unauthorized access to subject.")
                    return redirect("teacher_subjects")
                
                # Attach validated PyMongo subject_doc to request
                request.subject_doc = subject_doc
            else:
                request.subject_doc = None
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_teacher_subject_access(view_func):
    """
    Convenience shorthand decorator for teacher views needing subject validation.
    Usage:
        @login_required(login_url="login")
        @require_teacher_subject_access
        def view_name(request, ...):
            ...
    """
    return require_subject_access()(view_func)
