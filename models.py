from flask import flash
from app import db
from app.models import Turma, Enrollment, User, LessonAttendance, Lesson
import app.assignments.models

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
			lesson_attendance.append(lesson_dict)
		
		attendance_record.append((user, turma, lesson_attendance))
			
	return attendance_record