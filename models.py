from flask import flash, current_app, send_from_directory
from flask_login import current_user
from app import db, executor, pinyin
from app.models import Turma, Enrollment, User, LessonAttendance, Lesson, Assignment, ClassLibraryFile
import app.assignments.models
import pusher
import random
from datetime import datetime, date


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

	def add(self):
		db.session.add(self)
		db.session.commit()

	def save(self):
		db.session.commit()

	def delete(self):
		db.session.delete(self)
		db.session.commit()

	
def add_teacher_to_class (teacher_id, turma_id):
	teacher = User.query.get (teacher_id)
	turma = Turma.query.get (turma_id)
	if teacher is None or turma is None:
		return
	teacher_ownership = ClassManagement (user_id = teacher_id, turma_id = turma_id)
	teacher_ownership.add ()


def new_turma_from_form(form):
	new_turma = Turma(turma_number=form.turma_number.data, turma_label=form.turma_label.data,
                   turma_term=form.turma_term.data,
                   turma_year=form.turma_year.data,
                   lesson_start_time=form.lesson_start_time.data,
                   lesson_end_time=form.lesson_end_time.data)

	db.session.add(new_turma)
	db.session.flush()  # Access new_turma.id field from db

	# Add the teacher as one of the class managers for this class
	class_management = ClassManagement(
            user_id=current_user.id,
            turma_id=new_turma.id
        )
	class_management.add()

	db.session.commit()


# Function to extract data from a Zoom invitation link
def parse_zoom_invitation_helper (zoom_invitation):
	
	# Zoom adds extra \r as opposed to iCal event, remove it to unify parsing
	zoom_invitation = zoom_invitation.replace('\r', '')

	try:
		# Meeting ID and passcode
		split = zoom_invitation.split('Meeting ID: ')
		meeting_details = split[1].split('\nPasscode: ')
		meeting_id = meeting_details[0]
		meeting_passcode = meeting_details[1]

		# Meeting URL
		meeting_url = zoom_invitation.split('Join Zoom Meeting\n')
		meeting_url = meeting_url[1].split('\nMeeting ID:')
		meeting_url = meeting_url[0]

		# Meeting date
		meeting_datetime_str = zoom_invitation.split('Time: ')
		meeting_datetime_str = meeting_datetime_str[1] # i.e., the second part of the split string
		meeting_datetime_str = meeting_datetime_str[0:21].strip() # i.e. the first characters with datetime
		meeting_datetime_object = datetime.strptime(meeting_datetime_str, '%b %d, %Y %I:%M %p')
		
		return {
			'meeting_url': meeting_url,
			'meeting_id': meeting_id,
			'meeting_passcode': meeting_passcode,
			'meeting_datetime_object': meeting_datetime_object
		}
		
	except:
		return {'error': 'Could not process the data.'}
	

def get_teacher_classes_from_teacher_id(teacher_id):
	# If the teacher isn't an owner of any class, then show all classes
	# This should not be the case for any non-superintendant user
	turmas = []
	for class_management in ClassManagement.query.filter_by(user_id=teacher_id).all():
		turmas.append(Turma.query.get(class_management.turma_id))
	return turmas


# Check if a teacher_id is registered as managing a turma
# This will return only directly registered classes, i.e., a superintendant will NOT see all classes
def check_if_turma_id_belongs_to_a_teacher(turma_id, teacher_id):
	# Build array of str(class IDs) managed by this teacher
	turma_id_array = []
	for class_management in ClassManagement.query.filter_by(user_id=teacher_id).all():
		turma_id_array.append (str(class_management.turma_id))

	# Check to see if the turma being tested is in the array of classes managed by this teacher
	if str(turma_id) in turma_id_array: return True
	else: return False


# Remove a teacher from all their classes
# Used when deleting a teacher
def remove_teacher_from_all_classes (user_id):
	for management_relationship in ClassManagement.query.filter_by (user_id = user_id):
		management_relationship.delete()

def get_teacher_classes_with_students_from_teacher_id (teacher_id):
	turmas = []
	for class_management in ClassManagement.query.filter_by(user_id=teacher_id).all():
		turma_dict = class_management.__dict__
		students = []
		for enrollment in Enrollment.query.filter_by (turma_id = class_management.turma_id).all():
			students.append (User.query.get(enrollment.user_id))
		turma_dict['students'] = students
		turmas.append (turma_dict)
	return turmas


# Function to split a class into groups, with a fixed amount of students per group
def generate_random_student_groups_with_fixed_amount_of_students (turma_id, amount_of_students_per_group):
	# Get all students signed up to this class
	students_in_turma = db.session.query(Enrollment, User).join(
		User, Enrollment.user_id == User.id).filter(Enrollment.turma_id == turma_id).all()

	# Set initial variables
	number_of_students = len(students_in_turma)
	amount_of_students_per_group = int(amount_of_students_per_group)
	
	# Initialise an empty teams array
	teams = []
	team_number = 1 
	
	while number_of_students > 0:
		
		# Make a random sample of students, based on the size of the class
		team = {
			'team_number': team_number,
			'members': []
		}
		
		# Check to see if this is the last group, i.e., if students left in the pool is greater than desired sample size
		# This should only happen on the last pass through
		#¡# Consider distributing the remainder equally through existing groups, rather than in a potentially much smaller group
		if (amount_of_students_per_group > len(students_in_turma)):
			amount_of_students_per_group = len(students_in_turma)

		# Main algo
		for enrollment, user in random.sample(students_in_turma, amount_of_students_per_group):
			# For each student, assemble a data object
			student_info = {
				'name': user.username,
				'pinyin': pinyin.get_pinyin(user.username, ' ', tone_marks='marks')
			}	
			team['members'].append(student_info)

			# Remove this student from the pool
			students_in_turma.remove ((enrollment, user))
			number_of_students -= 1
		
		# Append new group to groups array
		teams.append (team)
		team_number += 1

	return teams


# Function to divide a class into a certain number of groups
def generate_random_student_groups_with_fixed_amount_of_groups (turma_id, number_of_groups):
	# Get all students signed up to this class
	students_in_turma = db.session.query(Enrollment, User).join(
		User, Enrollment.user_id == User.id).filter(Enrollment.turma_id == turma_id).all()

	# Set initial variables
	number_of_students = len(students_in_turma)
	number_of_groups = int(number_of_groups)
	
	# Initialise an empty teams array
	teams = []
	team_number = 1 
	
	while number_of_students > 0 and number_of_groups > 0:
		
		# Make a random sample of students, based on the size of the class
		team = {
			'team_number': team_number,
			'members': []
		}

		for enrollment, user in random.sample(students_in_turma, int(number_of_students/number_of_groups)):
			# For each student, assemble a data object
			student_info = {
				'name': user.username,
				'pinyin': pinyin.get_pinyin(user.username, ' ', tone_marks='marks')
			}	
			team['members'].append(student_info)

			# Remove this student from the pool
			students_in_turma.remove ((enrollment, user))
		
		# Iterate variables and append new group to groups array
		number_of_students -= int(number_of_students/number_of_groups)
		number_of_groups -= 1
		teams.append (team)
		team_number += 1
	
	return teams

def check_if_student_is_in_teachers_class(student_id, teacher_id):
	teacher_turmas = []
	for turma in get_teacher_classes_from_teacher_id(teacher_id):
		teacher_turmas.append(turma.id)

	for enrollment in Enrollment.query.filter_by(user_id=student_id).all():
		if enrollment.turma_id in teacher_turmas:
			return True

	# If no turmas matched, return false
	return False


def check_if_student_is_in_class (student_id, class_id):
	student = User.query.get (student_id)
	turma = Turma.query.get(class_id)

	if student is None or turma is None: return False

	enrollments = Enrollment.query.filter_by (user_id = student_id).filter_by(turma_id = class_id).all()
	if len(enrollments) > 0:
		return True
	else:
		return False

def get_class_enrollment_from_class_id(class_id):
	return db.session.query(
		Enrollment, Turma, User).join(
		Turma, Enrollment.turma_id == Turma.id).join(
		User, Enrollment.user_id == User.id).filter(
		Enrollment.turma_id == class_id).all()


def remove_all_enrollment_from_user (user_id):
	# Remove all enrollments
	for enrollment in Enrollment.query.filter_by (user_id = user_id):
		db.session.delete(enrollment)
		db.session.commit ()


def get_attendance_status(lesson_id, user_id):
	attendance = LessonAttendance.query.filter(
		LessonAttendance.lesson_id == lesson_id).filter(
		LessonAttendance.user_id == user_id).first()
	if attendance is not None:
		return attendance
	else:
		return False


def get_lesson_attendance_stats(lesson_id):
	record = {}
	lesson = Lesson.query.get(lesson_id)
	turma = Turma.query.get(lesson.turma_id)
	students_in_class = Enrollment.query.filter(
		Enrollment.turma_id == turma.id).all()
	record['students_in_class'] = len(students_in_class)

	attendance = LessonAttendance.query.filter(
		LessonAttendance.lesson_id == lesson_id).all()
	record['attendance'] = len(attendance)

	return record


def get_attendance_record(user_id):
	user_enrollment = app.assignments.models.get_user_enrollment_from_id(user_id)
	attendance_record = []
	for enrollment, user, turma in user_enrollment:
		# Get list of lessons for each class
		lessons = Lesson.query.filter(Lesson.turma_id == turma.id)

		# For each lesson, check if the user was present or not
		lesson_attendance = []
		for lesson in lessons:
			lesson_dict = lesson.__dict__
			lesson_dict['attended'] = get_attendance_status(lesson.id, user_id)
			lesson_dict['justification'] = get_absence_justification(lesson.id, user.id)
			lesson_attendance.append(lesson_dict)

		attendance_record.append((user, turma, lesson_attendance))

	return attendance_record


def get_user_attendance_record_stats(user_id, percentage=False):
	record = {}
	record['total_lessons_count'] = 0
	record['lessons_attended'] = 0

	user_enrollment = app.assignments.models.get_user_enrollment_from_id(user_id)
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
	else:
		return record

# Return a list of lessons that are today
def get_user_lessons_today_from_id(user_id):
	lessons_today = []
	for enrollment, user, turma in app.assignments.models.get_user_enrollment_from_id(user_id):
		for lesson in Lesson.query.filter_by(turma_id=turma.id):
			if lesson.date == date.today():
				lessons_today.append((lesson, turma))

	return lessons_today


# Return a collection of teacher lessons that are today
def get_teacher_lessons_today_from_teacher_id (teacher_id):
	lessons_today = []
	for turma in get_teacher_classes_from_teacher_id(teacher_id):
		for lesson in Lesson.query.filter_by(turma_id=turma.id):
			if lesson.date == date.today():
				lessons_today.append((lesson, turma))
	return lessons_today


def get_absence_justification(lesson_id, user_id):
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


def register_student_attendance(user_id, lesson_id, channel, disable_pusher=False):
	attendance = LessonAttendance(user_id=user_id,
                               lesson_id=lesson_id,
                               timestamp=datetime.now())

	db.session.add(attendance)
	db.session.commit()
	if disable_pusher is not False:
		push_attendance_to_pusher(User.query.get(user_id).username, channel)


def push_attendance_to_pusher(username, channel):
	pusher_client = pusher.Pusher(
            app_id=current_app.config['PUSHER_APP_ID'],
            key=current_app.config['PUSHER_KEY'],
            secret=current_app.config['PUSHER_SECRET'],
            cluster=current_app.config['PUSHER_CLUSTER'],
            ssl=current_app.config['PUSHER_SSL']
	)
	data = {"username": username}
	pusher_client.trigger(channel, 'new-record', {'data': data})


def new_absence_justification_from_form(form, lesson_id):
	file = form.absence_justification_file.data
	random_filename = app.files.models.save_file(file)
	original_filename = app.files.models.get_secure_filename(file.filename)

	new_absence_justification = AbsenceJustificationUpload(
            user_id=current_user.id,
            original_filename=original_filename,
            filename=random_filename,
            justification=form.justification.data,
            lesson_id=lesson_id,
            timestamp=datetime.now())

	db.session.add(new_absence_justification)
	db.session.commit()

	# Generate thumbnail
	executor.submit(app.files.models.get_thumbnail,
	                new_absence_justification.filename)

# Download an absence justification


def download_absence_justification(absence_justification_id):
	absence_justification = AbsenceJustificationUpload.query.get(
		absence_justification_id)
	return send_from_directory(filename=absence_justification.filename,
                            directory=current_app.config['UPLOAD_FOLDER'],
                            as_attachment=True,
                            attachment_filename=absence_justification.original_filename)

# Delete absence justification


def delete_absence_justification(absence_justification_id):
	absence_justification = AbsenceJustificationUpload.query.get(
		absence_justification_id)
	db.session.delete(absence_justification)
	db.session.commit()


# Delete all user absence justification uploads
def delete_all_user_absence_justification_uploads(user_id):
	absence_justications = AbsenceJustificationUpload.query.filter_by(
		user_id=user_id).all()
	if absence_justications is not None:
		for justification in absence_justications:
			db.session.delete(justification)
	db.session.commit()

# Method called when deleting a user


def delete_all_user_attendance_records(user_id):
	# Delete all the user attendance records
	attendances = LessonAttendance.query.filter_by(user_id=user_id).all()
	if attendances is not None:
		for attendance in attendances:
			db.session.delete(attendance)
	db.session.commit()


def delete_class_from_id(turma_id):
	for assignment in Assignment.query.filter(Assignment.target_turma_id == turma_id).all():
		app.assignments.models.delete_assignment_from_id(assignment.id)

	ClassLibraryFile.query.filter(ClassLibraryFile.turma_id == turma_id).delete()

	Enrollment.query.filter(Enrollment.turma_id == turma_id).delete()

	ClassManagement.query.filter(ClassManagement.turma_id == turma_id).delete()

	for lesson in Lesson.query.filter_by(turma_id=turma_id):
		AttendanceCode.query.filter(AttendanceCode.lesson_id == lesson.id).delete()
		AbsenceJustificationUpload.query.filter(
			AbsenceJustificationUpload.lesson_id == lesson.id).delete()
		LessonAttendance.query.filter(
			LessonAttendance.lesson_id == lesson.id).delete()

		db.session.delete(lesson)

	Turma.query.filter(Turma.id == turma_id).delete()

	db.session.commit()
