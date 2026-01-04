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

    # Legacy Memory module configuration
    MEMORY_DB_URI = os.environ.get('MEMORY_DB_URI', 'sqlite:///memory.db')

    # Puppeteer module configuration
    PUPPETEER_HEADLESS = os.environ.get('PUPPETEER_HEADLESS', 'true').lower() in ('true', '1', 't')
    CHROME_PATH = os.environ.get('CHROME_PATH', '/usr/bin/chromium-browser')

    # =========================================================================
    # Tiered Memory System Configuration
    # =========================================================================

    # Profile: S (Single machine), C (Cluster), E (Enterprise)
    MEMORY_PROFILE = os.environ.get('MEMORY_PROFILE', 'S')

    # Base path for local storage (Profile S)
    MEMORY_BASE_PATH = os.environ.get('MEMORY_BASE_PATH', 'data')

    # T1 Hot Cache Configuration
    MEMORY_T1_MAX_ITEMS = int(os.environ.get('MEMORY_T1_MAX_ITEMS', '10000'))
    MEMORY_T1_TTL = int(os.environ.get('MEMORY_T1_TTL', '3600'))  # seconds

    # Valkey Configuration (Profile C/E) - Redis-compatible
    VALKEY_URL = os.environ.get('VALKEY_URL', os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))

    # T2 Warm Index Configuration
    MEMORY_T2_DB_PATH = os.environ.get('MEMORY_T2_DB_PATH', 'data/memory_t2.db')
    MEMORY_POSTGRES_URL = os.environ.get('MEMORY_POSTGRES_URL')

    # T3 Cold Lake Configuration
    MEMORY_T3_PATH = os.environ.get('MEMORY_T3_PATH', 'data/t3')
    MEMORY_S3_BUCKET = os.environ.get('MEMORY_S3_BUCKET')
    MEMORY_S3_ENDPOINT = os.environ.get('MEMORY_S3_ENDPOINT')  # MinIO endpoint

    # T4 Audit Log Configuration
    MEMORY_T4_PATH = os.environ.get('MEMORY_T4_PATH', 'data/audit')
    MEMORY_WORM_ENABLED = os.environ.get('MEMORY_WORM_ENABLED', 'false').lower() in ('true', '1', 't')

    # Promotion/Demotion Thresholds
    MEMORY_HEAT_T3_T2 = float(os.environ.get('MEMORY_HEAT_T3_T2', '5.0'))
    MEMORY_HEAT_T2_T1 = float(os.environ.get('MEMORY_HEAT_T2_T1', '20.0'))
    MEMORY_DEMOTION_HOURS_T1_T2 = int(os.environ.get('MEMORY_DEMOTION_HOURS_T1_T2', '24'))
    MEMORY_DEMOTION_DAYS_T2_T3 = int(os.environ.get('MEMORY_DEMOTION_DAYS_T2_T3', '7'))
