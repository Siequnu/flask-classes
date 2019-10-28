from flask import render_template, flash, redirect, url_for, request, abort, current_app, session, Response
from flask_login import current_user, login_required

from app.classes import bp, models, forms
from app.classes.forms import TurmaCreationForm, LessonForm, AbsenceJustificationUploadForm

from app.files import models
from app.models import Turma, Lesson, LessonAttendance, AttendanceCode, User, Enrollment, AbsenceJustificationUpload
import app.models

from app import db

import datetime, uuid, random

import flask_excel as excel
import pusher

@bp.route("/create", methods=['GET', 'POST'])
@login_required
def create_class():
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		form = forms.TurmaCreationForm()
		del form.edit 
		if form.validate_on_submit():
			Turma.new_turma_from_form (form)
			flash('Class successfully created!', 'success')
			return redirect(url_for('classes.class_admin'))
		return render_template('classes/class_form.html', title='Create new class', form=form)
	abort(403)
	
	
@bp.route("/edit/<turma_id>", methods=['GET', 'POST'])
@login_required
def edit_class(turma_id):	
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		turma = Turma.query.get(turma_id)
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
		Turma.delete_turma_from_id(turma_id)
		flash('Class ' + str(turma_id) + ' has been deleted.', 'success')
		return redirect(url_for('classes.class_admin'))		
	abort (403)
	
	
@bp.route("/admin")
@login_required
def class_admin():
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		classes_array = Turma.query.all()
		return render_template('classes/class_admin.html', title='Class admin', classes_array = classes_array)
	abort (403)
	
	
@bp.route("/attendance/<class_id>")
@login_required
def class_attendance(class_id):
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		turma = Turma.query.get(class_id)
		lessons_array = []
		lessons = Lesson.query.filter(Lesson.turma_id == class_id).all()
		for lesson in lessons:
			lesson_dict = lesson.__dict__
			lesson_dict['attendance_stats'] = app.classes.models.get_lesson_attendance_stats (lesson.id)
			lessons_array.append(lesson_dict)
			
		return render_template('classes/class_attendance.html', title='Class attendance', turma = turma, lessons = lessons_array)
	abort (403)
	
	
@bp.route("/lesson/create/<class_id>", methods = ['POST', 'GET'])
@login_required
def create_lesson(class_id):
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		turma = Turma.query.get(class_id)
		form = LessonForm(start_time = turma.lesson_start_time,
						  end_time = turma.lesson_end_time,
						  date = datetime.datetime.now())
		del form.edit
		if form.validate_on_submit():
			lesson = Lesson(start_time = form.start_time.data,
							end_time = form.end_time.data,
							date = form.date.data,
							turma_id = turma.id)
			db.session.add(lesson)
			db.session.commit()
			flash ('New lesson added for ' + turma.turma_label + '.', 'success')
			return redirect (url_for('classes.class_attendance', class_id = turma.id))
		return render_template('classes/lesson_form.html', title='Create lesson', turma = turma, form = form)
	abort (403)
	

@bp.route("/lesson/delete/<lesson_id>", methods=['GET', 'POST'])
@login_required
def delete_lesson(lesson_id):	
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		try:
			# Delete all attendance for the lesson
			lesson_attendance = LessonAttendance.query.filter(LessonAttendance.lesson_id == lesson_id)
			if lesson_attendance is not None:
				for attendance in lesson_attendance:
					db.session.delete(attendance)			
			
			# Delete any open registration codes
			registration_codes = AttendanceCode.query.filter(AttendanceCode.lesson_id == lesson_id)
			if registration_codes is not None:
				for registration_code in registration_codes:
					db.session.delete(registration_code)	
			
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
		try:
			lesson = Lesson.query.get(lesson_id)
			turma = Turma.query.get(lesson.turma_id)
		except:
			flash ('Could not locate the lesson you wanted', 'error')
			return redirect (url_for('classes.class_admin'))
		
		# Add new attendance code to the database
		lines = open('eff_large_wordlist.txt').read().splitlines()
		code = random.choice(lines)
		code = code[6:]
		
		url = url_for ('classes.register_attendance', attendance_code = code, _external = True)
		attendance_code_object = AttendanceCode (code = code, lesson_id = lesson_id)
		db.session.add(attendance_code_object)
		db.session.commit()
		
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
	
	
@bp.route("/attendance/code/", methods = ['GET', 'POST'])
@login_required
def enter_attendance_code():
	# If admin, redirect to the class admin page
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		return redirect(url_for('classes.class_admin'))
	if request.values.get('attendance'):
		return redirect(url_for('classes.register_attendance', attendance_code = request.values.get('attendance')))
	greeting = app.main.models.get_greeting()
	return render_template('classes/enter_attendance_code.html', greeting = greeting)
	
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
		
		attendance_code_object = AttendanceCode.query.filter(AttendanceCode.code == attendance_code).first()
		#!# Check if user has already signed up for this lesson
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
			pusher_client.trigger('attendance', 'new-record', {'data': data })
		
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
				app.classes.models.register_student_attendance(user.id, lesson_id, disable_pusher = True)
				
		flash ('Marked entire class as attending', 'success')
		
		return redirect(url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
	abort (403)

@bp.route("/attendance/present/<user_id>/<lesson_id>")
@login_required
def register_student_as_attending(user_id, lesson_id):
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
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
				pusher_client.trigger('attendance', 'new-record', {'data': data })
			
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
			db.session.commit
			flash ('Student attendance removed', 'success')
			return redirect (url_for('classes.view_lesson_attendance', lesson_id = lesson_id))
		except:
			flash ('Could not find the attendance record.', 'error')
			return redirect (url_for('classes.class_admin'))
	
	abort (403)
	
	
@bp.route("/attendance/record/")
@bp.route("/attendance/record/<user_id>")
@login_required
def view_attendance_record(user_id = False):
	if user_id: # Admin can override the current_user by submitting a user_id
		attendance_record = app.classes.models.get_attendance_record(user_id)
		user = User.query.get(user_id)
	else:
		attendance_record = app.classes.models.get_attendance_record(current_user.id)
		user = User.query.get(current_user.id)
	return render_template('classes/view_attendance_record.html',
						   title='Attendance record',
						   attendance_record = attendance_record,
						   user = user)
	

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
		if current_user.is_authenticated and app.models.is_admin(current_user.username) or current_user.id == user.id:
			return app.classes.models.download_absence_justification(absence_justification_id)
		else:
			abort (403)
	except:
		flash('Could not locate the absence justification record!', 'error')
		return redirect(url_for('classes.view_attendance_record'))
	

@bp.route('/absence/justification/delete/<absence_justification_id>')
@login_required
def delete_absence(absence_justification_id):
	try:
		absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
		user = User.query.get(absence_justification.user_id)
		if current_user.is_authenticated and app.models.is_admin(current_user.username) or current_user.id == user.id:
			flash('Deleted student absence justification.', 'success')
			return app.classes.models.delete_absence_justification(absence_justification_id)
		else:
			abort (403)
	except:
		flash('Could not locate the absence justification record!', 'error')
		return redirect(url_for('classes.view_attendance_record'))


@bp.route("/export/<class_id>")
@login_required
def export_class_data(class_id):
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
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
		class_enrollment = app.classes.models.get_class_enrollment_from_class_id(class_id)
		return render_template('classes/class_enrollment.html', title='Class enrollment', class_enrollment = class_enrollment)
	abort (403)
	

@bp.route("/enrollment/remove/<enrollment_id>")
@login_required
def remove_enrollment(enrollment_id):
	if current_user.is_authenticated and app.models.is_admin(current_user.username):
		class_id = Enrollment.query.get(enrollment_id).turma_id
		Enrollment.query.filter(Enrollment.id==enrollment_id).delete()
		db.session.commit()
		flash('Student removed from class!', 'success')
		return redirect(url_for('classes.manage_enrollment', class_id = class_id))
	abort (403)
	
