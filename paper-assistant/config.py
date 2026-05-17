import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "papers.db"))
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "sk-4dd15e3cd49d4b648861276b5e1ecbac")

# Dify workflow configuration (takes precedence over direct Claude API)
DIFY_BASE_URL = os.environ.get("DIFY_BASE_URL", "http://localhost/v1")
DIFY_PAPER_ANALYSIS_KEY = os.environ.get("DIFY_PAPER_ANALYSIS_KEY", "app-MAjYTM2jjk9Ow7SC8FvwY3X3")
DIFY_SLIDE_GEN_KEY = os.environ.get("DIFY_SLIDE_GEN_KEY", "app-R2DBbvLlTKFf8bSW1204pJYr")
