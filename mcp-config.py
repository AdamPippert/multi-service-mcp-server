# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
    
    # GitHub module configuration
    GITHUB_API_URL = os.environ.get('GITHUB_API_URL', 'https://api.github.com')
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    
    # GitLab module configuration
    GITLAB_API_URL = os.environ.get('GITLAB_API_URL', 'https://gitlab.com/api/v4')
    GITLAB_TOKEN = os.environ.get('GITLAB_TOKEN')
    
    # Google Maps module configuration
    GMAPS_API_KEY = os.environ.get('GMAPS_API_KEY')
    
    # Memory module configuration
    MEMORY_DB_URI = os.environ.get('MEMORY_DB_URI', 'sqlite:///memory.db')
    
    # Puppeteer module configuration
    PUPPETEER_HEADLESS = os.environ.get('PUPPETEER_HEADLESS', 'true').lower() in ('true', '1', 't')
    CHROME_PATH = os.environ.get('CHROME_PATH', '/usr/bin/chromium-browser')
