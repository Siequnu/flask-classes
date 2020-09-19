from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, DateField, SelectMultipleField, BooleanField, FormField, TextAreaField, FileField
from wtforms.validators import ValidationError, DataRequired
from flask_wtf.file import FileField, FileRequired
from app import db
	
class TurmaCreationForm(FlaskForm):
	turma_number = StringField('Class number', validators=[DataRequired()], render_kw={"placeholder": "PS232"})
	turma_label = StringField('Class label', validators=[DataRequired()], render_kw={"placeholder": "Public Speaking 2-3"})
	turma_term = StringField('Class term', validators=[DataRequired()], render_kw={"placeholder": "Fall"})
	turma_year = StringField('Class year', validators=[DataRequired()], render_kw={"placeholder": "2020"})
	lesson_start_time = StringField('Class start time', validators=[DataRequired()], render_kw={"placeholder": "8:00"})
	lesson_end_time = StringField('Class end time', validators=[DataRequired()], render_kw={"placeholder": "9:30"})
	edit = SubmitField('Edit class')
	submit = SubmitField('Create class')
	
class LessonForm(FlaskForm):
	start_time = StringField('Class start time', validators=[DataRequired()])
	end_time = StringField('Class end time', validators=[DataRequired()])
	online_lesson_invitation = StringField('Zoom online lesson invitation', render_kw={"placeholder": "Paste Zoom invitation here"})
	online_lesson_code = StringField('Online lesson code')
	online_lesson_password = StringField('Online lesson password')
	date = DateField('Class date', validators=[DataRequired()])
	edit = SubmitField('Edit lesson')
	new_lesson_form_submit = SubmitField('Create lesson')
	
	
class AbsenceJustificationUploadForm(FlaskForm):
	absence_justification_file = FileField(label='Absence justification document:', validators=[DataRequired()])
	justification = TextAreaField('Justify your absence:', validators=[DataRequired()])
	submit = SubmitField('Submit')


class ClassBulkEmailForm(FlaskForm):
	subject = StringField('Subject line', validators=[DataRequired()])
	body = TextAreaField('Email message:', validators=[DataRequired()])
	submit = SubmitField('Send')