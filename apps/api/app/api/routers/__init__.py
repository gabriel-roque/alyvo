"""Version-one HTTP routers.

Compatibility modules keep the public routes stable while the composition root
uses the new API package boundary.
"""

from app.routers import auth, backoffice, chat, operations

__all__ = ["auth", "backoffice", "chat", "operations"]
