from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

import app.models  # noqa: F401,E402
