from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

UPLOAD_DIR = PROJECT_ROOT / "uploads"
CHART_DIR = PROJECT_ROOT / "charts"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR.mkdir(parents=True, exist_ok=True)