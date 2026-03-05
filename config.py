import os
from dotenv import load_dotenv

# Load environment variables — root .env first, then chatbot/.env as fallback
load_dotenv()
_chatbot_env = os.path.join(os.path.dirname(__file__), "chatbot", ".env")
if not os.getenv("SUPABASE_URL") and os.path.exists(_chatbot_env):
    load_dotenv(dotenv_path=_chatbot_env)

class Config:
    """Application configuration"""

    # Flask settings
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

    # Supabase (shared with chatbot)
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
    
    # Grok API settings (using Groq API which is compatible)
    GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
    GROQ_API_BASE = "https://api.groq.com/openai/v1"
    GROQ_MODEL = "mixtral-8x7b-32768"  # Groq's model
    
    # File upload settings
    UPLOAD_FOLDER = 'uploads'
    OUTPUT_FOLDER = 'outputs'
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'tiff'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # OCR Configuration
    OCR_ENABLED = True
    OCR_LANGUAGES = ['en']  # Add more languages as needed
    OCR_CONFIDENCE_THRESHOLD = 0.6
    
    # NLP Configuration
    NLP_ENABLED = True
    NLP_MODEL = 'en_core_web_sm'
    ENTITY_EXTRACTION_ENABLED = True
    
    # Template settings
    TEMPLATE_TYPES = {
        'type1': 'Detailed Itemized Quotation',
        'type2': 'Executive Summary Style'
    }
    
    @staticmethod
    def init_app(app):
        """Initialize application with config"""
        # Create necessary directories
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)
