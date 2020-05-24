from flask import Blueprint

bp = Blueprint('classes', __name__, template_folder='templates')

from app.classes import routes, models, forms