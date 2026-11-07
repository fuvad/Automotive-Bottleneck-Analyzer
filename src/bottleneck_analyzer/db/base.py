"""Shared SQLAlchemy declarative base for future mappings."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for PostgreSQL entity models."""
