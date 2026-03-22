# ============================================
# MAIN FLASK APPLICATION
# ============================================

import os

from flask import Flask, render_template
from flask_cors import CORS

from config import DATABASE_URL, MODELS_DIR, SECRET_KEY, UPLOAD_DIR
from database import db
from gemini_chat import GeminiChatbot
from ml_engine import MediMindML
from routes import api_bp


app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../frontend",
    static_url_path="/static",
)

app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

CORS(app)
db.init_app(app)

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.ml_engine = MediMindML(MODELS_DIR)
app.chatbot = GeminiChatbot(app.ml_engine)

app.register_blueprint(api_bp)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
