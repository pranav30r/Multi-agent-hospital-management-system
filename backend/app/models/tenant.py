from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now


class Tenant(Base):
    """
    Tenant domain entity representing a hospital or facility deployment boundary.
    Serves as the root boundary for multi-tenant data isolation.
    """
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        String(50), 
        primary_key=True, 
        default=lambda: f"TEN-{uuid.uuid4().hex[:8].upper()}"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Facility Contact & Metadata
    contact_phone: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
