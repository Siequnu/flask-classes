from flask import render_template, flash, redirect, url_for, request, abort, current_app, session, Response, jsonify
from flask_login import current_user, login_required

from app.classes import bp, models, forms
from app.classes.forms import TurmaCreationForm, LessonForm, AbsenceJustificationUploadForm, ClassBulkEmailForm
from app.classes.models import AbsenceJustificationUpload, AttendanceCode, ClassManagement

from app.files import models
from app.models import Turma, Lesson, LessonAttendance, User, Enrollment, Assignment, ClassLibraryFile
from app.assignments.models import delete_assignment_from_id
import app.models
import app.email_model

from app import db, executor

import datetime, uuid, random

import flask_excel as excel
import pusher

## API routes
# Parse a Zoom URL code
# Returns False if parsing fails
@bp.route("/api/parse/", methods = ['POST'])
@login_required
def parse_zoom_invitation ():
    if app.models.is_admin (current_user.username):
        return jsonify (app.classes.models.parse_zoom_invitation_helper (request.json['zoomInvitation']))
    abort (403)


# Return a list of classes belonging to this user_id
@bp.route("/api/classes/list/")
@login_required
def get_turmas_list_api ():
    turmas = []

    if current_user.is_superintendant is True:
        turma_choices = Turma.query.all ()
    elif app.models.is_admin (current_user.username):
        turma_choices = app.classes.models.get_teacher_classes_from_teacher_id (current_user.id)
    else: abort (403)

    for turma in turma_choices:
        turmas.append ({
            'id': turma.id,
            'label': turma.turma_label
        })

    return jsonify (turmas)

# Return a list of users and classes
@bp.route("/api/groups/", methods = ['POST'])
@login_required
def get_student_groups():
    if app.models.is_admin (current_user.username):

        if request.json['generationType'] == 'students per group':
            turma_id = request.json['turma']
            amount_of_students_per_group = request.json['userChoice']
            return jsonify (app.classes.models.generate_random_student_groups_with_fixed_amount_of_students (turma_id, amount_of_students_per_group))

        elif request.json['generationType'] == 'groups':
            turma_id = request.json['turma']
            amount_of_groups = request.json['userChoice']
            return jsonify (app.classes.models.generate_random_student_groups_with_fixed_amount_of_groups (turma_id, amount_of_groups))

        else: return jsonify ({'error': 'Did not recognise the request type.'})

    # If not admin, abort
    abort (403)

# Create a new class
@bp.route("/api/lesson/create", methods = ['POST'])
@login_required
def create_lesson_api ():
    if app.models.is_admin (current_user.username):
        try:
            lesson_objects = request.json['lessonObjects']
            for lesson_object in lesson_objects:

                lesson = Lesson(
                    start_time = lesson_object['startTime'],
                    end_time = lesson_object['endTime'],
                    date = lesson_object['date'],
                    turma_id = lesson_object['turmaId']
                )
                db.session.add(lesson)
                db.session.commit()

            flash ('All lessons added successfully', 'success')
            return jsonify ({'success': 'All lessons added successfully.'})

        except:
            flash ('An error occured while adding the lessons', 'error')
            return jsonify ({'error': 'An error occured while adding the lessons.'})
    abort (403)

# API route to add an enrollment
@bp.route("/api/enrollment/add/<student_id>/<turma_id>", methods = ['POST'])
@login_required
def add_enrollment_api(student_id, turma_id):
    if app.models.is_admin (current_user.username):
        try:
            # Check if the student exists and exit if not
            student = User.query.get(student_id)
            print (student)
            if student is None:
                return jsonify ({'error': 'Could not locate this student in the database.'})

            # Check if the class exists and exit if not
            turma = Turma.query.get(turma_id)
            print (turma)
            if turma is None:
                return jsonify ({'error': 'Could not locate this class in the database.'})

            # If the current user isn't managing this class, exit.
            # Superintendants will not pass this step, they are counted as a normal teacher
            if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma_id, current_user.id) is False:
                abort (403)

            # Enroll the student in the classs
            app.assignments.models.enroll_user_in_class(student_id, turma_id)
            return jsonify ({'success': 'Student added successfully.'})
        except:
            return jsonify ({'error': 'An error occured while enrolling the student.'})

    abort (403)


## GUI routes
@bp.route("/create", methods=['GET', 'POST'])
@login_required
def create_class():
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        form = forms.TurmaCreationForm()
        del form.edit
        if form.validate_on_submit():
            app.classes.models.new_turma_from_form (form)
            flash('Class successfully created!', 'success')
            return redirect(url_for('classes.class_admin'))
        return render_template('classes/class_form.html', title='Create new class', form=form)
    abort(403)


@bp.route("/edit/<turma_id>", methods=['GET', 'POST'])
@login_required
def edit_class(turma_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turma = Turma.query.get(turma_id)

        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        form = TurmaCreationForm(obj=turma)
        del form.submit # Leaves the edit submit button

        if form.validate_on_submit():
            form.populate_obj(turma)
            db.session.add(turma)
            db.session.commit()
            flash('Class edited successfully!', 'success')
            return redirect(url_for('classes.class_admin'))
        return render_template('classes/class_form.html', title='Edit class', form=form)
    abort(403)


@bp.route("/delete/<turma_id>")
@login_required
def delete_class(turma_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turma = Turma.query.get (turma_id)

        if turma is None:
            flash ('Could not find the class!', 'error')

        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        # Delete all files and class management entries to do with this turma
        app.classes.models.delete_class_from_id (turma_id)

        flash('Class ' + str(turma_id) + ' has been deleted.', 'success')
        return redirect(url_for('classes.class_admin'))

    abort (403)


@bp.route("/admin")
@login_required
def class_admin():
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        classes_array = app.classes.models.get_teacher_classes_from_teacher_id (current_user.id)
        return render_template('classes/class_admin.html', title='Class admin', classes_array = classes_array)
    abort (403)


# Page to assign classes to teachers
@bp.route("/management")
@login_required
def class_ownership_management():
    if current_user.is_authenticated and current_user.is_superintendant:
        classes_array = Turma.query.all()
        teachers = User.query.filter_by (is_admin = True).all()
        for turma in classes_array:
            turma_dict = turma.__dict__

            current_teacher_assignments = ClassManagement.query.filter_by (turma_id = turma.id).all()
            turma_dict['current_teachers'] = []
            for teaching_assignment in current_teacher_assignments:
                turma_dict['current_teachers'].append (User.query.get (teaching_assignment.user_id))

            turma_dict['available_teachers'] = {teacher for teacher in teachers if teacher not in turma_dict['current_teachers']}
        teachers = User.query.filter_by (is_admin = True).all()
        return render_template('classes/class_ownership_management.html', title='Class ownership management', classes_array = classes_array, teachers = teachers)
    abort (403)


# Method to assign teachers to a class
@bp.route("/management/add/<int:teacher_id>/to/<int:class_id>")
@login_required
def assign_teacher_to_class(teacher_id, class_id):
    if current_user.is_authenticated and current_user.is_superintendant:
        teacher = User.query.get (teacher_id)
        turma = Turma.query.get (class_id)
        if teacher is None or turma is None:
            flash ('Could not find this teacher or class', 'error')
        teacher_ownership = ClassManagement (user_id = teacher_id, turma_id = class_id)
        teacher_ownership.add ()
        flash ('Added ' + teacher.username + ' to ' + turma.turma_label, 'success')
        return redirect (url_for('classes.class_ownership_management'))
    abort (403)


# Method to remove teachers from a class
@bp.route("/management/remove/<int:teacher_id>/from/<int:class_id>")
@login_required
def remove_teacher_from_class(teacher_id, class_id):
    if current_user.is_authenticated and current_user.is_superintendant:
        teacher = User.query.get (teacher_id)
        turma = Turma.query.get (class_id)
        if teacher is None or turma is None:
            flash ('Could not find this teacher or class', 'error')
        teacher_ownership = ClassManagement.query.filter_by (user_id = teacher_id).filter_by (turma_id = class_id).all()
        for item in teacher_ownership:
            item.delete ()
        flash ('Removed ' + teacher.username + ' from ' + turma.turma_label, 'success')
        return redirect (url_for('classes.class_ownership_management'))
    abort (403)


# Class to view all lessons and summarised attendance stats
# Defaults to view all, accepts 'future' to only see future classes
@bp.route("/attendance/<class_id>")
@bp.route("/attendance/<class_id>/<view>")
@login_required
def class_attendance(class_id, view=False):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):

        turma = Turma.query.get(class_id)

        if turma is None:
            abort (404)

        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        # Get the lessons, ordered by date ascending
        lessons_array = []
        lessons = Lesson.query.filter(Lesson.turma_id == class_id).order_by(Lesson.date.asc()).all()

        # New lesson form (embedded in modal)
        form = LessonForm (
            start_time = turma.lesson_start_time,
            end_time = turma.lesson_end_time,
            date = datetime.datetime.now()
        )
        del form.edit

        for lesson in lessons:
            lesson_dict = lesson.__dict__
            lesson_dict['attendance_stats'] = app.classes.models.get_lesson_attendance_stats (lesson.id)
            lessons_array.append(lesson_dict)

        # If we have included a view variable in the URL, update the desired view and save it to session
        if view: # i.e., navigating here with purpose to change the view, otherwise defaults to False
            session['lessonsViewAs'] = view

        # Filter the lessons, if filter is saved in session
        if session.get('lessonsViewAs') == 'future':

            flash ('You are currently viewing only future lessons', 'info')

            future_lessons = []
            for lesson in lessons_array:
                if lesson['date'] >= datetime.date.today():
                    future_lessons.append (lesson)
            lessons_array = future_lessons


        return render_template(
            'classes/class_attendance.html',
            view = session.get('lessonsViewAs'),
            title='Class attendance',
            turma = turma,
            lessons = lessons_array,
            date = datetime.datetime.now(),
            form = form)
    abort (403)


@bp.route("/lesson/create/<class_id>", methods = ['POST', 'GET'])
@login_required
def create_lesson(class_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turma = Turma.query.get(class_id)

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        form = LessonForm(start_time = turma.lesson_start_time,
                          end_time = turma.lesson_end_time,
                          date = datetime.datetime.now())
        del form.edit
        if form.validate_on_submit():
            # Extract lesson data from pasted Zoom message
            meeting_url = ''
            meeting_id = ''
            meeting_passcode = ''

            try:

                if form.online_lesson_invitation.data:
                    split = form.online_lesson_invitation.data.split('Meeting ID: ')
                    split = split[1].split ('\n')
                    meeting_details = split[0].split(' Passcode: ')
                    meeting_id = meeting_details[0]
                    meeting_passcode = meeting_details[1]

                    meeting_url = form.online_lesson_invitation.data.split('Join Zoom Meeting ')
                    meeting_url = meeting_url[1].split('  Meeting ID:')
                    meeting_url = meeting_url[0]

                # Overwrite auto-generated details if these were given
                if form.online_lesson_code.data:
                    meeting_id = form.online_lesson_code.data

                if form.online_lesson_password.data:
                    meeting_passcode = form.online_lesson_password.data
            except:
                flash ('An error occured while parsing the Zoom invitation. The lesson has been created without a Zoom code.')

            lesson = Lesson(start_time = form.start_time.data,
                            end_time = form.end_time.data,
                            online_lesson_code = meeting_id,
                              online_lesson_password = meeting_passcode,
                            online_lesson_url = meeting_url,
                            date = form.date.data,
                            turma_id = turma.id)
            db.session.add(lesson)
            db.session.commit()
            flash ('New lesson added for ' + turma.turma_label + '.', 'success')
            return redirect (url_for('classes.class_attendance', class_id = turma.id))
        return render_template('classes/lesson_form.html', title='Create lesson', turma = turma, form = form)
    abort (403)

@bp.route("lesson/create/bulk/<turma_id>")
@login_required
def bulk_create_lessons (turma_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turma = Turma.query.get(turma_id)

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        return render_template('classes/bulk_create_lessons.html', title='Bulk create lessons', turma = turma)


@bp.route("/lesson/delete/<lesson_id>", methods=['GET', 'POST'])
@login_required
def delete_lesson(lesson_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        lesson = Lesson.query.get (lesson_id)
        if lesson is None: abort (403)

        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (lesson.turma_id, current_user.id) is False:
            abort (403)

        try:
            # Delete all attendance for the lesson
            for attendance in LessonAttendance.query.filter(LessonAttendance.lesson_id == lesson_id):
                db.session.delete(attendance)

            # Delete any open registration codes
            for registration_code in AttendanceCode.query.filter(AttendanceCode.lesson_id == lesson_id):
                db.session.delete(registration_code)

            # Delete any uploaded absence justification
            for absence_justification_upload in AbsenceJustificationUpload.query.filter_by (lesson_id = lesson_id).all():
                db.session.delete (absence_justification_upload)

            # Delete the lesson
            lesson = Lesson.query.get(lesson_id)
            class_id = lesson.turma_id
            db.session.delete(lesson)
            db.session.commit()

            flash('Lesson removed!', 'success')
            return redirect(url_for('classes.class_attendance', class_id = class_id))
        except:
            flash('Could not delete the lesson!', 'error')
            return redirect(url_for('classes.class_admin'))
    abort(403)


@bp.route("/attendance/qr/<lesson_id>/")
@login_required
def open_attendance(lesson_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):

        lesson = Lesson.query.get(lesson_id)
        if lesson is None: abort (404)

        turma = Turma.query.get(lesson.turma_id)
        if turma is None: abort (404)

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        # Check to see if we have a prior open code, to avoid refreshing the code
        prior_code = AttendanceCode.query.filter_by(lesson_id=lesson_id).first()
        if (prior_code):
            attendance_code_object = prior_code
            code = prior_code.code

        else:
            print ('creating new code')
            # Add new attendance code to the database
            lines = open('eff_large_wordlist.txt').read().splitlines()
            code = random.choice(lines)
            code = code[6:]

            attendance_code_object = AttendanceCode (code = code, lesson_id = lesson_id)
            db.session.add(attendance_code_object)
            db.session.commit()

        url = url_for ('classes.register_attendance', attendance_code = code, _external = True)
        return render_template('classes/lesson_attendance_qr_code.html',
                               title='Class attendance',
                               turma = turma,
                               attendance_code_object = attendance_code_object,
                               url = url,
                               code = code,
                               greeting = app.main.models.get_greeting(),
                               )
    abort (403)


@bp.route("/attendance/close/<attendance_code_id>/")
@login_required
def close_attendance(attendance_code_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        try:
            attendance_code_object = AttendanceCode.query.get(attendance_code_id)
            lesson = Lesson.query.get(attendance_code_object.lesson_id)
            turma = Turma.query.get(lesson.turma_id)

            # Remove attendance code
            db.session.delete(attendance_code_object)
            db.session.commit()

            flash ('Attendance closed for ' + turma.turma_label + '.', 'success')
            return redirect (url_for('classes.class_attendance', class_id = turma.id))
        except:
            flash ('Could not find this attendance code', 'error')
            return redirect (url_for('classes.class_admin'))
    abort (403)


@bp.route("/attendance/view/<lesson_id>/")
@login_required
def view_lesson_attendance(lesson_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        try:
            lesson = Lesson.query.get(lesson_id)
            turma = Turma.query.get(lesson.turma_id)

            if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
                abort (403)

            attendance_stats = app.classes.models.get_lesson_attendance_stats (lesson_id)

            class_enrollment = app.classes.models.get_class_enrollment_from_class_id (lesson.turma_id)
            attendance_array = []
            for enrollment, turma, user in class_enrollment:
                user_dict = user.__dict__
                user_dict['attendance'] = app.classes.models.get_attendance_status (lesson_id, user.id)
                user_dict['justification'] = app.classes.models.get_absence_justification (lesson_id, user.id)

                attendance_array.append(user_dict)

        except:
            flash ('Could not locate the lesson you wanted', 'error')
            return redirect (url_for('classes.class_admin'))

        return render_template('classes/view_lesson_attendance.html',
                               title='Lesson attendance',
                               turma = turma,
                               lesson = lesson,
                               attendance_array = attendance_array,
                               attendance_stats = attendance_stats)
    abort (403)


@bp.route("/absence/justifications/view")
@login_required
def view_all_absence_justifications():
    # Assemble all absence justifications with additional user, lesson and turma data
    absence_justifications = db.session.query(AbsenceJustificationUpload, User, Lesson, Turma).join(
                User, AbsenceJustificationUpload.user_id == User.id).join(
                Lesson, AbsenceJustificationUpload.lesson_id == Lesson.id).join(
            Turma, Lesson.turma_id == Turma.id).all()

    # Unpack absence justifications and add an indication if this has been approved
    # There is no direct way to do this, but we can check to see if student has been registerd as attending
    # However, there is no indication as to whether a justification has been ignored, or denied
    # Possible later development can add an approved/denied flag
    appended_absence_justifications = []
    for absence_justification, user, lesson, turma in absence_justifications:
        absence_justification_dict = absence_justification.__dict__
        absence_justification_dict['student_is_marked_as_attending'] = app.classes.models.check_if_student_has_attendend_this_lesson (user.id, lesson.id)
        appended_absence_justifications.append ((absence_justification_dict, user, lesson, turma))

    # Overwrite the original
    absence_justifications = appended_absence_justifications

    # Return as-is if the user is a superintendant
    if current_user.is_authenticated and current_user.is_superintendant and request.args.get('view') != 'normal':
            return render_template(
                'classes/view_all_absence_justifications.html',
                absence_justifications=absence_justifications)

    # If user is a standard teacher, or superintendant
    elif current_user.is_authenticated and app.models.is_admin(current_user.username):
        filtered_absence_justifications = []

        # For each justification
        for absence_justification, user, lesson, turma in absence_justifications:

            # Check if the user who wrote it is in the teacher's class
            if app.classes.models.check_if_student_is_in_teachers_class (user.id, current_user.id):
                filtered_absence_justifications.append ((absence_justification, user, lesson, turma))

        return render_template('classes/view_all_absence_justifications.html',
                              absence_justifications = filtered_absence_justifications)

    abort (403)

@bp.route("/attendance/code/", methods = ['GET', 'POST'])
@login_required
def enter_attendance_code():
    # If admin, redirect to the class admin page
    # #¡# This redirect isn't being used anymore, is it? Can delete admin if flag
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        return redirect(url_for('classes.class_admin'))

    # If the form has been posted (and we now have a value in the URL)
    if request.values.get('attendance'):
        return redirect(url_for('classes.register_attendance', attendance_code = request.values.get('attendance')))

    # Main loader
    greeting = app.main.models.get_greeting()
    lessons_today = app.classes.models.get_user_lessons_today_from_id (current_user.id)
    return render_template('classes/enter_attendance_code.html', greeting = greeting, lessons_today = lessons_today)

@bp.route("/attendance/register/<attendance_code>/")
@login_required
def register_attendance(attendance_code):
    try:
        pusher_client = pusher.Pusher(
            app_id= current_app.config['PUSHER_APP_ID'],
            key = current_app.config['PUSHER_KEY'],
            secret=current_app.config['PUSHER_SECRET'],
            cluster=current_app.config['PUSHER_CLUSTER'],
            ssl=current_app.config['PUSHER_SSL']
        )

        # Get the attendance code object
        attendance_code_object = AttendanceCode.query.filter(AttendanceCode.code == attendance_code).first()

        # Get the lesson object to know the turma_id for Pusher
        lesson = Lesson.query.get(attendance_code_object.lesson_id)

        if attendance_code_object is None or lesson is None:
            flash ('Could not find the lesson you want to register for.', 'error')
            return redirect (url_for('main.index'))

        # Check if user is part of this class, if not, reject their sign-up attempt
        if app.classes.models.check_if_student_is_in_class (student_id = current_user.id, class_id = lesson.turma_id) is False:
            flash ('You are trying to register for a class in which you are not enrolled. Please ask your teacher for help.', 'warning')
            return redirect (url_for('main.index'))

        # Check if user has already signed up for this lesson
        if LessonAttendance.query.filter(
                LessonAttendance.lesson_id == attendance_code_object.lesson_id).filter(
                LessonAttendance.user_id == current_user.id).first() is not None:

            flash ('You have already registered your attendance.', 'info')

        else: # User not registered yet, sign 'em up.
            attendance = LessonAttendance (user_id = current_user.id,
                                       lesson_id = attendance_code_object.lesson_id,
                                       timestamp = datetime.datetime.now())
            db.session.add(attendance)
            db.session.commit()

            data = {"username": current_user.username}
            channel = str(lesson.turma_id)
            pusher_client.trigger(channel, 'new-record', {'data': data })

    except:
        flash ('Your code was invalid', 'info')
        return redirect (url_for('main.index'))
    return redirect (url_for('classes.attendance_success'))


@bp.route("/attendance/register/batch/<lesson_id>")
@login_required
def batch_register_lesson_as_attended(lesson_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        lesson = Lesson.query.get(lesson_id)

        class_enrollment = app.classes.models.get_class_enrollment_from_class_id (lesson.turma_id)

        for enrollment, turma, user in class_enrollment:
            if app.classes.models.check_if_student_has_attendend_this_lesson(user.id, lesson_id) is not True:
                app.classes.models.register_student_attendance(user.id, lesson_id, channel= str(lesson.turma_id), disable_pusher = True)

        flash ('Marked entire class as attending', 'success')

        return redirect(url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
    abort (403)

@bp.route("/attendance/present/<user_id>/<lesson_id>")
@login_required
def register_student_as_attending(user_id, lesson_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        user = User.query.get(user_id)

        # Get the turma_id from the lesson_id, for the Pusher channel
        lesson = Lesson.query.get(lesson_id)

        if User is None or lesson is None:
            abort (404)
        else:
            username = user.username
        try:
            pusher_client = pusher.Pusher(
                app_id= current_app.config['PUSHER_APP_ID'],
                key = current_app.config['PUSHER_KEY'],
                secret=current_app.config['PUSHER_SECRET'],
                cluster=current_app.config['PUSHER_CLUSTER'],
                ssl=current_app.config['PUSHER_SSL']
            )

            #!# Check if user has already signed up for this lesson
            if app.classes.models.check_if_student_has_attendend_this_lesson (user_id, lesson_id) is True:
                flash ('This student is already registered in this lesson.', 'info')

            else: # User not registered yet, sign 'em up.
                attendance = LessonAttendance (user_id = user_id,
                                           lesson_id = lesson_id,
                                           timestamp = datetime.datetime.now())
                db.session.add(attendance)
                db.session.commit()
                username = User.query.get(user_id).username
                data = {"username": username}
                channel = str(lesson.turma_id)
                pusher_client.trigger(channel, 'new-record', {'data': data })

        except:
            flash ('Could not register student as attending', 'warning')
            return redirect (url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
        flash ('Marked ' + username + ' as in attendance', 'success')
        return redirect (url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
    abort (403)


@bp.route("/attendance/register/success")
@login_required
def attendance_success():
    return render_template('classes/lesson_attendance_completed.html',
                           title='Class attendance',
                           greeting = app.main.models.get_greeting())



@bp.route("/attendance/remove/<attendance_id>")
@login_required
def remove_attendance(attendance_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        try:
            attendance = LessonAttendance.query.get(attendance_id)
            lesson_id = attendance.lesson_id
            db.session.delete(attendance)
            db.session.commit()
            flash ('Student attendance removed', 'success')
            return redirect (url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
        except:
            flash ('Could not find the attendance record.', 'error')
            return redirect (url_for('classes.class_admin'))

    abort (403)

@bp.route("/attendance/open/view")
@login_required
def view_open_attendance_codes ():
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        try:
            # Get all attendance codes for a superintendant
            if current_user.is_superintendant == True:
                attendance_codes = db.session.query(AttendanceCode).all()

            # Only get attendance codes for a teacher's classes
            else:
                attendance_codes = []
                for attendance_code in db.session.query(AttendanceCode).all():
                    lesson = Lesson.query.get (attendance_code.lesson_id)
                    if app.classes.models.check_if_turma_id_belongs_to_a_teacher (lesson.turma_id, current_user.id):
                        attendance_codes.append (attendance_code)

            return render_template('classes/view_open_attendance_codes.html', attendance_codes = attendance_codes)
        except:
            flash ('An error occured while viewing attendance codes.', 'error')
            return redirect (url_for('classes.class_admin'))

    abort (403)

@bp.route("/attendance/close/all")
@login_required
def close_all_attendance_codes ():
    if current_user.is_authenticated and app.models.is_admin(current_user.username):

        # Get all attendance codes for a superintendant
        if current_user.is_superintendant == True:
            attendance_codes = db.session.query(AttendanceCode).all()

        # Only get attendance codes for a teacher's classes
        else:
            attendance_codes = []
            for attendance_code in db.session.query(AttendanceCode).all():
                lesson = Lesson.query.get (attendance_code.lesson_id)
                if app.classes.models.check_if_turma_id_belongs_to_a_teacher (lesson.turma_id, current_user.id):
                    attendance_codes.append (attendance_code)

        for code in attendance_codes:
            db.session.delete(code)
            db.session.commit()
        flash ('Successfully deleted all open attendance codes', 'success')
        return redirect (url_for('classes.class_admin'))

    abort (403)


@bp.route("/attendance/record/")
@bp.route("/attendance/record/<user_id>")
@login_required
def view_attendance_record(user_id = False):
    if user_id and app.models.is_admin(current_user.username): # Admin can override the current_user by submitting a user_id
        attendance_record = app.classes.models.get_attendance_record(user_id)
        user = User.query.get(user_id)
    else:
        attendance_record = app.classes.models.get_attendance_record(current_user.id)
        user = User.query.get(current_user.id)
    return render_template('classes/view_attendance_record.html',
                           title='Attendance record',
                           attendance_record = attendance_record,
                           user = user)
'''
@bp.route("/class/attendance/<class_id>/")
@login_required
def view_class_attendance_record():
    if user_id and app.models.is_admin(current_user.username):
        turma = Turma.query.get(class_id)

        # Get students enrolled in this class

        # Get the lesson record for this class
        lessons = Lesson.query.filter(Lesson.turma_id == turma_id)

        user = User.query.get(user_id)
    return render_template('classes/view_class_attendance_record.html',
                           title='Attendance record',
                           attendance_record = attendance_record,
                           user = user)
'''


@bp.route('/absence/justification/<lesson_id>', methods=['GET', 'POST'])
@login_required
def upload_absence_justification (lesson_id):
    # If current student was present at the class, no need to justify absence!
    if app.classes.models.check_if_student_has_attendend_this_lesson (current_user.id, lesson_id) is True:
        flash ('You are registered in this class and do not need to upload a justification.', 'info')
        return redirect(url_for('classes.view_attendance_record'))

    form = forms.AbsenceJustificationUploadForm()
    if form.validate_on_submit():
        app.classes.models.new_absence_justification_from_form(form, lesson_id)
        flash('New justification uploaded successfully!', 'success')
        return redirect(url_for('classes.view_attendance_record'))
    return render_template('classes/upload_absence_justification.html', title='Upload absence justification', form=form)


@bp.route('/absence/view/<absence_justification_id>')
@login_required
def view_absence_justification (absence_justification_id):
    #!# Need to delete any absence statements when deleting a user
    try:
        absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
        user = User.query.get(absence_justification.user_id)
        lesson = Lesson.query.get(absence_justification.lesson_id)
        turma = Turma.query.get(lesson.turma_id)

        # Check if the current student is viewing their own justification
        if current_user.id == absence_justification.user_id:
            pass
        # Or else, if the current user_id manages the class this justification is for
        # If not, abort
        elif app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        # Only admin or absence_justification uploader can view this justification
        if current_user.is_authenticated and app.models.is_admin(current_user.username) or current_user.id == user.id:
            return render_template('classes/view_absence_justification.html',
                           title='View absence justification',
                           absence_justification = absence_justification,
                           user = user,
                           lesson = lesson,
                           turma = turma)
        else:
            abort (403)
    except:
        flash('Could not locate the absence justification record!', 'error')
        return redirect(url_for('classes.view_attendance_record'))


@bp.route('/absence/justification/download/<absence_justification_id>')
@login_required
def download_absence_justification(absence_justification_id):
    try:
        absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
        user = User.query.get(absence_justification.user_id)
        lesson = Lesson.query.get(absence_justification.lesson_id)
        turma = Turma.query.get(lesson.turma_id)

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        if current_user.is_authenticated and app.models.is_admin(current_user.username) or current_user.id == user.id:
            return app.classes.models.download_absence_justification(absence_justification_id)
        else:
            abort (403)
    except:
        flash('Could not locate the absence justification record!', 'error')
        return redirect(url_for('classes.view_attendance_record'))


@bp.route('/absence/justification/delete/<absence_justification_id>')
@login_required
def delete_absence_justification(absence_justification_id):
    try:
        absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
        lesson_id = absence_justification.lesson_id
        user = User.query.get(absence_justification.user_id)
        lesson = Lesson.query.get(absence_justification.lesson_id)
        turma = Turma.query.get(lesson.turma_id)

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        if current_user.is_authenticated and app.models.is_admin(current_user.username) or current_user.id == user.id:
            app.classes.models.delete_absence_justification(absence_justification_id)
            flash('Deleted student absence justification.', 'success')
            return redirect(url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
        else:
            abort (403)
    except:
        flash('Could not locate the absence justification record!', 'error')
        return redirect(url_for('classes.view_attendance_record'))


@bp.route("/export/<class_id>")
@login_required
def export_class_data(class_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (class_id, current_user.id) is False:
            abort (403)

        query_sets = db.session.query(User).join(
            Enrollment, Enrollment.user_id == User.id).filter(
            Enrollment.turma_id == class_id).order_by(User.student_number.asc()).all()
        class_object = Turma.query.get(class_id)
        filename = class_object.turma_label + ' - ' + class_object.turma_term + ' ' + str(class_object.turma_year)
        column_names = ['student_number', 'username', 'email']
        return excel.make_response_from_query_sets(query_sets, column_names, "xlsx", file_name = filename)
    abort (403)


@bp.route("/enrollment/<class_id>")
@login_required
def manage_enrollment(class_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (class_id, current_user.id) is False:
            abort (403)

        # Get the current enrollment
        class_enrollment = app.classes.models.get_class_enrollment_from_class_id(class_id)

        # Get the current non-enrolled list
        not_enrolled_in_class = app.classes.models.get_students_not_enrolled_in_class(class_id)

        return render_template(
            'classes/class_enrollment.html',
            title='Class enrollment',
            turma_id = class_id,
            class_enrollment = class_enrollment,
            not_enrolled_in_class = not_enrolled_in_class)
    abort (403)


@bp.route("/enrollment/remove/<enrollment_id>")
@login_required
def remove_enrollment(enrollment_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        class_id = Enrollment.query.get(enrollment_id).turma_id

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (class_id, current_user.id) is False:
            abort (403)

        Enrollment.query.filter(Enrollment.id==enrollment_id).delete()
        db.session.commit()
        flash('Student removed from class!', 'success')
        return redirect(url_for('classes.manage_enrollment', class_id = class_id))
    abort (403)


# Send a bulk class email
@bp.route("/email/bulk/<class_id>", methods=['GET', 'POST'])
def send_bulk_email_to_class(class_id):
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turma = Turma.query.get(class_id)

        # Check if current user is registered as a class manager
        if app.classes.models.check_if_turma_id_belongs_to_a_teacher (turma.id, current_user.id) is False:
            abort (403)

        users = app.classes.models.get_class_enrollment_from_class_id(class_id)
        user_emails = ''
        for enrollment, turma, user in users:
            user_emails += ' ' + user.email

        form = ClassBulkEmailForm()
        if form.validate_on_submit():
            subject = form.subject.data
            body = render_template(
                'email/blank_template.html',
                body = form.body.data,
                subject = subject,
                app_name = current_app.config['APP_NAME']
                )
            executor.submit(app.email_model.send_email(user_emails, subject, body))
            flash ('Sent a bulk email to all students in ' + turma.turma_label)
            return redirect(url_for('classes.class_admin'))
        return render_template('classes/bulk_email_class.html', title='Send a message to the class',
                               turma = turma,
                               users = users,
                               form = form)
    abort (403)


# Random student generator
@bp.route("/student/random", methods=['GET'])
def random_student_generator ():
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turmas = app.classes.models.get_teacher_classes_from_teacher_id (current_user.id)
        return render_template('classes/random_student_generator.html', turmas = turmas)


# Group generator
@bp.route("/group/generate", methods=['GET'])
def group_generator ():
    if current_user.is_authenticated and app.models.is_admin(current_user.username):
        turmas = app.classes.models.get_teacher_classes_from_teacher_id (current_user.id)
        return render_template('classes/group_generator.html', turmas = turmas)
