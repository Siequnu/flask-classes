from flask import flash, current_app, send_from_directory
from flask_login import current_user
from app import db, executor
from app.models import Turma, Enrollment, User, LessonAttendance, Lesson, AbsenceJustificationUpload
import app.assignments.models
import pusher
import datetime

def get_class_enrollment_from_class_id (class_id):
	return db.session.query(
		Enrollment, Turma, User).join(
		Turma, Enrollment.turma_id==Turma.id).join(
		User, Enrollment.user_id==User.id).filter(
		Enrollment.turma_id == class_id).all()

def get_attendance_status (lesson_id, user_id):
	attendance = LessonAttendance.query.filter(
		LessonAttendance.lesson_id == lesson_id).filter(
		LessonAttendance.user_id == user_id).first()
	if attendance is not None:
		return attendance
	else:
		return False

def get_attendance_record (user_id):
	user_enrollment = app.assignments.models.get_user_enrollment_from_id (user_id)
	attendance_record = []
	for enrollment, user, turma in user_enrollment:
		# Get list of lessons for each class
		lessons = Lesson.query.filter(Lesson.turma_id == turma.id)
		
		# For each lesson, check if the user was present or not
		lesson_attendance = []
		for lesson in lessons:
			lesson_dict = lesson.__dict__
			lesson_dict['attended'] = get_attendance_status(lesson.id, user_id)
			lesson_dict['justification'] = get_absence_justification (lesson.id, user.id)
			lesson_attendance.append(lesson_dict)
		
		attendance_record.append((user, turma, lesson_attendance))
			
	return attendance_record


def get_absence_justification (lesson_id, user_id):
	justification = AbsenceJustificationUpload.query.filter(
		AbsenceJustificationUpload.lesson_id == lesson_id).filter(
		AbsenceJustificationUpload.user_id == user_id).first()
	if justification is not None:
		return justification
	else:
		return False

def check_if_student_has_attendend_this_lesson(user_id, lesson_id):
	if LessonAttendance.query.filter(
			LessonAttendance.lesson_id == lesson_id).filter(
			LessonAttendance.user_id == user_id).first() is not None:
		return True
	else:
		return False
	
def register_student_attendance (user_id, lesson_id):
	attendance = LessonAttendance (user_id = user_id,
								lesson_id = lesson_id,
								timestamp = datetime.datetime.now())
	db.session.add(attendance)
	db.session.commit()
	push_attendance_to_pusher( User.query.get(user_id).username)
	
def push_attendance_to_pusher (username):
	pusher_client = pusher.Pusher(
				app_id= current_app.config['PUSHER_APP_ID'],
				key = current_app.config['PUSHER_KEY'],
				secret=current_app.config['PUSHER_SECRET'],
				cluster=current_app.config['PUSHER_CLUSTER'],
				ssl=current_app.config['PUSHER_SSL']
	)
	data = {"username": username}
	pusher_client.trigger('attendance', 'new-record', {'data': data })
	
	
def new_absence_justification_from_form (form, lesson_id):
	file = form.absence_justification_file.data
	random_filename = app.files.models.save_file(file)
	original_filename = app.files.models.get_secure_filename(file.filename)

	new_absence_justification = AbsenceJustificationUpload (
					user_id = current_user.id,
					original_filename = original_filename,
					filename = random_filename,
					justification = form.justification.data,
					lesson_id = lesson_id,
					timestamp = datetime.datetime.now())

	db.session.add(new_absence_justification)
	db.session.commit()
	
	# Generate thumbnail
	executor.submit(app.files.models.get_thumbnail, new_absence_justification.filename)
	

def download_absence_justification (absence_justification_id):
	absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
	return send_from_directory(filename=absence_justification.filename,
								   directory=current_app.config['UPLOAD_FOLDER'],
								   as_attachment = True,
								   attachment_filename = absence_justification.original_filename)

