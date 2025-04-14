from flask import Blueprint, render_template
from services.model_provider import ModelProvider

views_bp = Blueprint('views', __name__)
model_provider = ModelProvider()

@views_bp.route('/')
def index():
    models = model_provider.get_available_models()
    return render_template('index.html', models=models)