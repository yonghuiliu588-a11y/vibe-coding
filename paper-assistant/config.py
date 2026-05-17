import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
IMAGES_DIR = os.environ.get("IMAGES_DIR", os.path.join(BASE_DIR, "uploads", "images"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "papers.db"))
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "sk-4dd15e3cd49d4b648861276b5e1ecbac")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# Dify workflow configuration (takes precedence over direct Claude API)
DIFY_BASE_URL = os.environ.get("DIFY_BASE_URL", "http://localhost/v1")
DIFY_PAPER_ANALYSIS_KEY = os.environ.get("DIFY_PAPER_ANALYSIS_KEY", "app-WPQWJWgDpxSFvAZ0ddiduhxR")
DIFY_SLIDE_GEN_KEY = os.environ.get("DIFY_SLIDE_GEN_KEY", "app-eJM63yF4fj1F1HC6TcC1t622")
DIFY_CHAT_ASSISTANT_KEY = os.environ.get("DIFY_CHAT_ASSISTANT_KEY", "app-pDen5wLZyMTznK8iJnu1aM7I")
