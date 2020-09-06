from flask import flash, current_app, send_from_directory
from flask_login import current_user
from app import db, executor
from app.models import Turma, Enrollment, User, LessonAttendance, Lesson
import app.assignments.models
import pusher
from datetime import datetime

class AttendanceCode (db.Model):
	__table_args__ = {'sqlite_autoincrement': True}
	id = db.Column(db.Integer, primary_key=True)
	code = db.Column(db.String(140))
	lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'))
	
	def __repr__(self):
		return '<Attendance Code {}>'.format(self.code)
	
# Model used to store absence justifications, where a student can upload a file after being classed as absent in a class
class AbsenceJustificationUpload(db.Model):
	__table_args__ = {'sqlite_autoincrement': True}
	id = db.Column(db.Integer, primary_key=True)
	original_filename = db.Column(db.String(140))
	filename = db.Column(db.String(140))
	justification = db.Column(db.String(1500))
	timestamp = db.Column(db.DateTime, default=datetime.now())
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'))
	
	def __repr__(self):
		return '<Absence Justification Upload {}>'.format(self.original_filename)

# Model used to store teacher-class relationships, whereby an admin can view all classes, 
# but can choose only to see certain classes in the interface, i.e., the assignments or class attendance pages
class ClassManagement(db.Model):
	__table_args__ = {'sqlite_autoincrement': True}
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	turma_id = db.Column(db.Integer, db.ForeignKey('turma.id'))
	
	def __repr__(self):
		return '<Class Management relationship {}>'.format(self.id)

	def add (self):
		db.session.add (self)
		db.session.commit()

	def save (self):
		db.session.commit()

	def delete (self):
		db.session.delete(self)
		db.session.commit()

def get_teacher_classes_from_teacher_id (teacher_id):
	classes_management_entries = ClassManagement.query.filter_by (user_id = teacher_id).all()
	# If the teacher isn't an owner of any class, then show all classes
	if classes_management_entries == []:
		return Turma.query.all()
	else:
		turmas = []
		for turma in classes_management_entries:
			turmas.append (Turma.query.get (turma.turma_id))
		return turmas

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
	

def get_lesson_attendance_stats (lesson_id):
	record = {}
	lesson = Lesson.query.get(lesson_id)
	turma = Turma.query.get(lesson.turma_id)
	students_in_class = Enrollment.query.filter(Enrollment.turma_id == turma.id).all()
	record['students_in_class'] = len(students_in_class)
	
	attendance = LessonAttendance.query.filter(
		LessonAttendance.lesson_id == lesson_id).all()
	record['attendance'] = len(attendance)
	
	return record
	
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

def get_user_attendance_record_stats (user_id, percentage = False):
	record = {}
	record['total_lessons_count'] = 0
	record['lessons_attended'] = 0
	
	user_enrollment = app.assignments.models.get_user_enrollment_from_id (user_id)
	for enrollment, user, turma in user_enrollment:	
		lessons = Lesson.query.filter(Lesson.turma_id == turma.id)
		record['total_lessons_count'] += lessons.count()
	
		for lesson in lessons:
			if get_attendance_status(lesson.id, user_id) is not False:
				record['lessons_attended'] += 1
	
	if percentage:
		if record['total_lessons_count'] == 0:
			return 100
		else:
			return int(float(record['lessons_attended']) * 100 / float(record['total_lessons_count']))
	else: return record


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
	
def register_student_attendance (user_id, lesson_id, disable_pusher = False):
	attendance = LessonAttendance (user_id = user_id,
								lesson_id = lesson_id,
								timestamp = datetime.now())
	db.session.add(attendance)
	db.session.commit()
	if disable_pusher is not False:
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
					timestamp = datetime.now())

	db.session.add(new_absence_justification)
	db.session.commit()
	
	# Generate thumbnail
	executor.submit(app.files.models.get_thumbnail, new_absence_justification.filename)
	
# Download an absence justification
def download_absence_justification (absence_justification_id):
	absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
	return send_from_directory(filename=absence_justification.filename,
								   directory=current_app.config['UPLOAD_FOLDER'],
								   as_attachment = True,
								   attachment_filename = absence_justification.original_filename)

# Delete absence justification
def delete_absence_justification (absence_justification_id):
	absence_justification = AbsenceJustificationUpload.query.get(absence_justification_id)
	db.session.delete(absence_justification)
	db.session.commit()
	

# Delete all user absence justification uploads
def delete_all_user_absence_justification_uploads (user_id):
	absence_justications = AbsenceJustificationUpload.query.filter_by(user_id=user_id).all()
	if absence_justications is not None:
		for justification in absence_justications:
			db.session.delete(justification)
	db.session.commit()

# Method called when deleting a user
def delete_all_user_attendance_records (user_id):
	# Delete all the user attendance records
	attendances = LessonAttendance.query.filter_by(user_id=user_id).all()
	if attendances is not None:
		for attendance in attendances:
			db.session.delete(attendance)
	db.session.commit()
