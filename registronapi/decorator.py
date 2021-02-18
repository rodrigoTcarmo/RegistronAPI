from django.shortcuts import redirect

# Decorator created to restrictions

def unauthenticated_user(view_func):
    def wrapper_func(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('main')
        else:
            return view_func(request, *args, **kwargs)

    return wrapper_func


def allowed_users(allowed_groups=[]):
    def decorator(view_func):
        def wrapper_func(request, *args, **kwargs):

            group = None
            if request.user.groups.exists():
                group = request.user.groups.all()[0].name

            if group in allowed_groups:
                return view_func(request, *args, **kwargs)
            else:
                return redirect('forbidden')
        return wrapper_func
    return decorator
