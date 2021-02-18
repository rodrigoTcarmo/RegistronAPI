from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from registrondeparts.models import Department
from registronapi.decorator import unauthenticated_user
from django.contrib.auth.models import Group


@login_required
def main(request): # Requests for the main page. Must be logged in for access.
    loged_user = request.user.username
    context = {'loged_user': loged_user}
    return render(request, 'main.html', context)


@login_required
def users(request): # Requests for the users page, here we can get a list of all users (according to your permissions)
    all_users = User.objects.all()
    all_users_depart = request.user.profile.department
    group = request.user.groups.all()[0].name
    loged_user = request.user.username

    context = {'users': all_users, 'user_depart': all_users_depart, 'group': group, 'loged_user': loged_user}

    return render(request, 'users/users.html', context)


@login_required
def user_detail(request, user_id): # Requests for user detail page, here we can see all details of a specific user (according to your permissions)
    user = User.objects.get(id=user_id)
    depart = user.profile.department
    fl_name = user.profile.full_name
    context = {'user': user, 'depart': depart, 'fl_name': fl_name}

    return render(request, 'users/user_detail.html', context)


@unauthenticated_user
def register(request): # Requests for register page, here, new users can register themselves (if you are logged in, you can't access this page)
    all_departs = Department.objects.all()
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        pwd = request.POST['password1']
        pwd_confirm = request.POST['password2']
        department = request.POST['department']
        full_name = request.POST['full_name']

        if pwd != pwd_confirm: # Here we confirm the two password given by the user
            messages = ['Incorrect password']
            context = {'all_departs': all_departs, 'messages': messages}
            return render(request, 'users/register.html', context)

        # Now its time to create the new user
        new_user = User.objects.create_user(username=username, email=email, password=pwd)
        new_user.save()
        new_user.profile.department = department
        new_user.profile.full_name = full_name
        new_user.save()

        # We are setting a default group for new users on django admin "Users"
        set_group = Group.objects.get(name='User')
        new_user.groups.add(set_group)

        # Here we authenticate the new user
        auth_user = authenticate(username=username, password=pwd)
        login(request, auth_user)
    else:
        context = {'all_departs': all_departs}
        return render(request, 'users/register.html', context)

    # Getting some info to redirect to the user detail page
    user = User.objects.get(username=username)
    depart = user.profile.department
    fl_name = user.profile.full_name
    context = {'user': user, 'depart': depart, 'fl_name': fl_name}
    return render(request, 'users/user_detail.html', context)


@login_required
def user_update(request, user_id): # Requests for update user profile (according to your permissions)
    user = User.objects.get(id=user_id)
    all_departs = Department.objects.all()
    depart = user.profile.department
    fl_name = user.profile.full_name

    # Here we get the new info
    if request.method == 'POST':
        email = request.POST['email']
        full_name = request.POST['full_name']
        department = request.POST['department']

        # Check for changes
        if email:
            user.email = email
            user.save()

        if full_name:
            user.profile.full_name = full_name
            user.save()

        if department:
            user.profile.department = department
            user.save()

        return redirect('users')

    context = {'all_departs': all_departs, 'fl_name': fl_name, 'depart': depart, 'user': user}
    return render(request, 'users/user_update.html', context)


@login_required
def user_delete(request, user_id): # Requests for delete users (according to your permissions)
    user_delete = User.objects.get(id=user_id) # Get the id of the user

    if request.method == 'POST':
        user_delete.delete()
        return redirect('users')

    context = {'user_delete': user_delete}

    return render(request, 'users/user_delete.html', context)


@unauthenticated_user
def do_login(request): # Authenticate user who trying to login
    if request.method == 'POST':
        auth_user = authenticate(username=request.POST['username'], password=request.POST['password'])
        if auth_user:
            login(request, auth_user)
            return redirect('main')
        else:
            messages = ['Incorrect password']

    return render(request, 'users/login.html', locals())


def do_logout(request): # Logout the user
    logout(request)
    return redirect('login')


def forbidden(request): # A forbidden page, appears when non-admin user try to access restricted area
    return render(request, 'forbidden.html')
