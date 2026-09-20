"""Delete expired anonymous sessions and cascading profile histories, never active sessions."""

from sqlalchemy import create_engine

from app.common.config import Settings
from app.profiles.service import ProfileService

if __name__ == "__main__":
    settings = Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        print(f"Removed {ProfileService(engine, settings).cleanup()} expired sessions.")
    finally:
        engine.dispose()
