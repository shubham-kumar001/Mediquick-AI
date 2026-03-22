import os

# API Keys - VERIFY THIS KEY IS VALID
GEMINI_API_KEY = "AIzaSyD01eMSuXa0xioT5SxNAnHmCaFlJ6qKXeY"

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, 'models')  # This should point to the models folder
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# Database
DATABASE_URL = "sqlite:///medimind.db"

# Flask Config
SECRET_KEY = "medimind-secret-key-2026"
DEBUG = True
