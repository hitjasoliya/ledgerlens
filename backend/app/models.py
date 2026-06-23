import datetime
import uuid
from sqlalchemy import Column, DateTime, String, Integer, Boolean, JSON
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="employee")  # "admin" or "employee"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_by = Column(String, nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    source = Column(String, nullable=False)
    uploaded_by_id = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    scope = Column(String, nullable=False, default="employee")
    access_list = Column(JSON, nullable=False, default=list)
    pages_parsed = Column(Integer, nullable=False, default=0)
    chunks_created = Column(Integer, nullable=False, default=0)
    chunks_indexed = Column(Integer, nullable=False, default=0)
    is_persistent = Column(Boolean, nullable=False, default=True)
    session_id = Column(String, nullable=True)

