from flask import Blueprint

bp = Blueprint('classes', __name__)

from app.classes import routes, models, forms