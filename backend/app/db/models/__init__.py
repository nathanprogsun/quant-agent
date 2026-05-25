from app.db.models.core.base import Base

# Import all models to register them with Base
from app.db.models.user import User

__all__ = ["Base", "User"]
