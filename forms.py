from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, DateField, SelectMultipleField, BooleanField, FormField, TextAreaField, FileField
from wtforms.validators import ValidationError, DataRequired
from flask_wtf.file import FileField, FileRequired
from app import db
	
class TurmaCreationForm(FlaskForm):
	turma_number = StringField('Class number', validators=[DataRequired()])
	turma_label = StringField('Class label', validators=[DataRequired()])
	turma_term = StringField('Class term', validators=[DataRequired()])
	turma_year = StringField('Class year', validators=[DataRequired()])
	lesson_start_time = StringField('Class start time', validators=[DataRequired()])
	lesson_end_time = StringField('Class end time', validators=[DataRequired()])
	edit = SubmitField('Edit class')
	submit = SubmitField('Create class')
	
class LessonForm(FlaskForm):
	start_time = StringField('Class start time', validators=[DataRequired()])
	end_time = StringField('Class end time', validators=[DataRequired()])
	date = DateField('Class date', validators=[DataRequired()])
	edit = SubmitField('Edit lesson')
	submit = SubmitField('Create lesson')
	
	
class AbsenceJustificationUploadForm(FlaskForm):
	absence_justification_file = FileField(label='Absence justification document:')
	justification = TextAreaField('Justify your absence:', validators=[DataRequired()])
	submit = SubmitField('Submit')


class ClassBulkEmailForm(FlaskForm):
	subject = StringField('Subject line', validators=[DataRequired()])
	body = TextAreaField('Email message:', validators=[DataRequired()])
	submit = SubmitField('Send')