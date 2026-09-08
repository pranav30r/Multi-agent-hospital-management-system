from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now

class Disease(Base):
    __tablename__ = "diseases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"DIS-{uuid.uuid4().hex[:6].upper()}")
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    icd_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="General Medicine")
    
    # Clinical Context Flags (NO severity_weight - vitals dictate triage priority!)
    is_communicable: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_isolation: Mapped[bool] = mapped_column(Boolean, default=False)
    
    added_by: Mapped[str] = mapped_column(String, nullable=False, default="REC-001")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
