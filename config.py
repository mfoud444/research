import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    UPLOAD_FOLDER = 'output'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123'
    MAX_RETRIES = 3
    INITIAL_DELAY = 1
    BACKOFF_FACTOR = 2
    AI_PROVIDER = os.getenv('AI_PROVIDER', 'g4f')  # Options: g4f, huggingface, together, openai
    
    AI_PROVIDER_CONFIG = {
        'g4f': {
            # g4f specific configuration
        },
        'huggingface': {
            'api_key': os.getenv('HUGGINGFACE_API_KEY'),
            'max_tokens': 1000,
            'temperature': 0.7
        },
        'together': {
            'api_key': os.getenv('TOGETHER_API_KEY'),
            'max_tokens': 1000,
            'temperature': 0.7
        },
         'openai': {
            'api_key': os.getenv('OPENAI_API_KEY'),
            'organization': os.getenv('OPENAI_ORG_ID'),
            'base_url': os.getenv('OPENAI_BASE_URL', "https://oral-una-sarr-e3334ca1.koyeb.app/v1"),  # Default OpenAI endpoint
            'max_tokens': 1000,
            'temperature': 0.7,
            'top_p': 0.9,
            'frequency_penalty': 0,
            'presence_penalty': 0
        },
            'g4f-api': {
            'base_url': 'https://oral-una-sarr-e3334ca1.koyeb.app/v1',
            'default_model': 'gpt-4o-mini'
        }
    }