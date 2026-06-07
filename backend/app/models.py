import datetime
import uuid
from sqlalchemy import Column, DateTime, String
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="employee")  # "admin" or "employee"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_by = Column(String, nullable=True)
