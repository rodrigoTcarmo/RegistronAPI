from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from registrondeparts.models import Department
from registronapi.decorator import allowed_users

@login_required
@allowed_users(allowed_groups=['Administrator'])
def register_depart(request): # Requests for create a new department (according to your permissions)
    if request.method == 'POST':
        all_departs = Department.objects.all()
        depart_name = request.POST['depart_name']
        Department.objects.get_or_create(department_name=depart_name)
        context = {'all_departs': all_departs}
        return render(request, 'departments.html', context)

    else:
        return render(request, 'depart_create.html')


@login_required
def departments(request): # Resquest to list your departments
    all_departs = Department.objects.all()
    context = {'all_departs': all_departs}
    return render(request, 'departments.html', context)

@login_required
@allowed_users(allowed_groups=['Administrator'])
def department_delete(request, depart_id): # Request to delete the department (according to your permissions)
    depart_delete = Department.objects.get(id=depart_id)
    if request.method == 'POST':
        depart_delete.delete()
        return redirect('departments')

    context = {'depart_delete': depart_delete}

    return render(request, 'department_delete.html', context)
