from flask import Flask, url_for
from config import Config
from routes.api import api_bp
from routes.views import views_bp

app = Flask(__name__)
app.config.from_object(Config)

# Register blueprints
app.register_blueprint(views_bp)
app.register_blueprint(api_bp, url_prefix='/api')

# if __name__ == '__main__':
#     app.run(debug=True)
