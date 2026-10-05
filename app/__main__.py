"""Run one camera-owning process: python -m app."""
import uvicorn

from .config import load_settings

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, workers=1)
