

from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test

from django.http import HttpResponseForbidden, HttpResponse
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.db.models import Q
import json
import pdfkit
from django.template.loader import render_to_string

from .models import CustomUser, Child, Questionnaire, ParentResponse
from .forms import CustomUserCreationForm, ChildForm, TherapistResponseForm


# Хелпер функции за проверка на роли
def is_admin(user):
    return user.is_authenticated and user.role == 'admin'


def is_therapist(user):
    return user.is_authenticated and user.role == 'therapist'


def is_parent(user):
    return user.is_authenticated and user.role == 'parent'


# Главна страна
def index(request):
    return render(request, "index.html")

# Прикажи прашалник
@login_required
def prasalnici(request, mesec):
    # Провери дали прашалникот постои во базата
    questionnaire = get_object_or_404(Questionnaire, months=mesec)

    with open(f"timski_proekt/Prasalnici/{mesec}meseci.json", encoding="utf-8") as f:
        quiz = json.load(f)

    if request.method == "GET":
        return render(request, "prasalnici.html", {"quiz": quiz, "mesec": mesec})

    # POST - зачувување на одговори
    elif request.method == "POST" and is_parent(request.user):
        child = request.user.children.first()
        if not child:
            return redirect('add_child')

        # Собирање на одговорите
        answers = {}

        for key, value in request.POST.items():

            if key == "csrfmiddlewaretoken":
                continue

            # textarea
            if key.startswith("txt_"):
                q_id = key.replace("txt_", "")

                if q_id not in answers:
                    answers[q_id] = {}

                answers[q_id]["text"] = value

            # radio answers
            elif not key.endswith("_command"):
                q_id = key

                if q_id not in answers:
                    answers[q_id] = {}

                answers[q_id]["answer"] = value

            # checkbox commands
            elif key.endswith("_command"):
                q_id = key.replace("_command", "")

                if q_id not in answers:
                    answers[q_id] = {}

                answers[q_id]["commands"] = request.POST.getlist(key)

        # Создај ParentResponse
        response = ParentResponse.objects.create(
            parent=request.user,
            child=child,
            questionnaire=questionnaire,
            answers_json=json.dumps(answers),
            notes=request.POST.get('notes', ''),
            status='submitted'
        )
        print(answers)
        return redirect('parent_dashboard')


# Регистрација (секогаш Parent)
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'parent'  # Секогаш parent при регистрација
            user.save()
            login(request, user)
            return redirect('add_child')  # Пренасочи кон додавање дете после регистрација
        else:
            # Прикажи грешки
            return render(request, 'registration/register.html', {'form': form})
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})
# Логин
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Пренасочување според улогата
            if user.role == 'admin':
                return redirect('admin_dashboard')
            elif user.role == 'therapist':
                return redirect('therapist_dashboard')
            else:
                return redirect('parent_dashboard')
        else:
            return render(request, 'registration/login.html', {'form': form})
    else:
        form = AuthenticationForm()

    # Зачувај ја next страницата ако постои
    next_page = request.GET.get('next', '')
    return render(request, 'registration/login.html', {'form': form, 'next': next_page})


# Logout
def logout_view(request):
    logout(request)
    return redirect('index')


# Parent Dashboard
@login_required
@user_passes_test(is_parent)
def parent_dashboard(request):
    responses = ParentResponse.objects.filter(parent=request.user).order_by('-created_at')
    children = request.user.children.all()
    return render(request, 'parent_dashboard.html', {
        'responses': responses,
        'children': children
    })


# Додади дете
@login_required
@user_passes_test(is_parent)
def add_child(request):
    if request.method == 'POST':
        form = ChildForm(request.POST)
        if form.is_valid():
            child = form.save(commit=False)
            child.parent = request.user
            child.save()
            return redirect('parent_dashboard')
    else:
        form = ChildForm()
    return render(request, 'add_child.html', {'form': form})


# Therapist Dashboard
@login_required
@user_passes_test(is_therapist)
def therapist_dashboard(request):
    # Прикажи ги сите одговори што чекаат на преглед
    responses = ParentResponse.objects.filter(status='submitted').order_by('-created_at')
    reviewed = ParentResponse.objects.filter(status='reviewed').order_by('-updated_at')
    return render(request, 'therapist_dashboard.html', {
        'pending_responses': responses,
        'reviewed_responses': reviewed
    })


# Therapist Response View
@login_required
@user_passes_test(is_therapist)
def therapist_response(request, response_id):
    parent_response = get_object_or_404(ParentResponse, id=response_id)

    if request.method == 'POST':
        # Обработка на поените
        points_data = {}
        total_points = 0

        for key, value in request.POST.items():
            if key.startswith('points_'):
                q_id = key.replace('points_', '')
                if value:
                    points = int(value)
                    points_data[q_id] = points
                    total_points += points

        # Зачувување на поените
        parent_response.therapist_points = json.dumps(points_data)
        parent_response.total_points = total_points
        parent_response.therapist_comments = request.POST.get('comments', '')
        parent_response.status = 'reviewed'
        parent_response.save()

        return redirect('therapist_dashboard')

    # GET - прикажи ја формата
    # Вчитај го прашалникот
    with open(f"timski_proekt/Prasalnici/{parent_response.questionnaire.months}meseci.json", encoding="utf-8") as f:
        quiz = json.load(f)

    # Вчитај ги одговорите од родителот
    answers = parent_response.get_answers()

    # Парсирај ги одговорите за полесен пристап во template
    parsed_answers = {}
    for key, value in answers.items():
        if isinstance(value, dict):
            # Ако имаме dict (може да е речник со команди и примероци)
            parsed_answers[key] = value
        else:
            # Ако е обичен стринг
            parsed_answers[key] = value

    therapist_points = parent_response.get_therapist_points()

    return render(request, 'therapist_response.html', {
        'response': parent_response,
        'quiz': quiz,
        'answers': parsed_answers,
        'therapist_points': therapist_points,
    })


# Admin Dashboard
@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    users = CustomUser.objects.all()
    responses = ParentResponse.objects.all().order_by('-created_at')

    parent_count = CustomUser.objects.filter(role='parent').count()
    therapist_count = CustomUser.objects.filter(role='therapist').count()
    total_children = Child.objects.count()

    avg_child_age = 0
    children = Child.objects.all()
    if children:
        total_months = sum(child.get_age_in_months() for child in children)
        avg_child_age = round(total_months / children.count())

    # Обработка на POST за додавање нов корисник
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # Земи ја улогата од формата
            role = request.POST.get('role', 'parent')
            user.role = role
            # Земи го телефонскиот број
            phone = request.POST.get('phone', '')
            if phone:
                user.phone = phone
            user.save()

            #messages.success(request, f'Корисникот {user.username} е успешно креиран!')
            return redirect('admin_dashboard')
        else:
            # Прикажи грешки
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = CustomUserCreationForm()

    context = {
        'users': users,
        'responses': responses,
        'parent_count': parent_count,
        'therapist_count': therapist_count,
        'total_children': total_children,
        'avg_child_age': avg_child_age,
        'form': form,  # Испрати ја формата до темплејтот
    }
    return render(request, 'admin_dashboard.html', context)
# Детали за Parent Response
@login_required
def response_detail(request, response_id):
    response = get_object_or_404(ParentResponse, id=response_id)

    # Проверка на пристап
    if not (request.user == response.parent or
            request.user.role == 'therapist' or
            request.user.role == 'admin'):
        return HttpResponseForbidden("Немате пристап до овој одговор")

    with open(f"timski_proekt/Prasalnici/{response.questionnaire.months}meseci.json", encoding="utf-8") as f:
        quiz = json.load(f)

    answers = response.get_answers()
    therapist_points = response.get_therapist_points()
    print(answers)
    return render(request, 'response_detail.html', {
        'response': response,
        'quiz': quiz,
        'answers': answers,
        'therapist_points': therapist_points
    })


@login_required
def export_response_pdf(request, response_id):
    # Земи го одговорот од база
    response = get_object_or_404(ParentResponse, id=response_id)

    # Проверка дали корисникот смее да гледа
    if not (request.user == response.parent or
            request.user.role == 'therapist' or
            request.user.role == 'admin'):
        return HttpResponseForbidden("Немате пристап до овој одговор")

    # Вчитај го прашалникот
    with open(f"timski_proekt/Prasalnici/{response.questionnaire.months}meseci.json", encoding="utf-8") as f:
        quiz = json.load(f)

    # Вчитај ги одговорите
    answers = response.get_answers()
    therapist_points = response.get_therapist_points()

    # Направи посебен HTML за PDF
    html_string = render_to_string('pdf_export.html', {
        'response': response,
        'quiz': quiz,
        'answers': answers,
        'therapist_points': therapist_points,
        'user': request.user,
    })
    print(answers)

    # Конфигурација за pdfkit - ПАТЕКАТА ДО wkhtmltopdf
    try:
        # Обиди се со стандардната патека
        config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')

        # Опции за подобар изглед
        options = {
            'page-size': 'A4',
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'margin-top': '20mm',
            'margin-right': '15mm',
            'margin-bottom': '20mm',
            'margin-left': '15mm',
        }

        # Направи PDF
        pdf = pdfkit.from_string(html_string, False, configuration=config, options=options)

    except Exception as e:
        # Ако не успее, пробај без конфигурација (ако wkhtmltopdf е во PATH)
        try:
            pdf = pdfkit.from_string(html_string, False, options=options)
        except:
            # Ако пак не успее, врати грешка
            return HttpResponse(f"Грешка при генерирање PDF: {str(e)}", status=500)

    # Врати го PDF-то како одговор
    response_pdf = HttpResponse(pdf, content_type='application/pdf')

    # Име на файлот
    filename = f"odgovor_{response.child.first_name}_{response.child.last_name}_{response.questionnaire.months}_meseci.pdf"
    response_pdf['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response_pdf