from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # DEP-ER, DEP-ICU, etc.
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(200), nullable=True)
    total_beds: Mapped[int] = mapped_column(Integer, default=0)
    current_occupancy: Mapped[int] = mapped_column(Integer, default=0)
    min_doctors: Mapped[int] = mapped_column(Integer, default=1)
    min_nurses: Mapped[int] = mapped_column(Integer, default=2)
    nurse_patient_ratio: Mapped[str] = mapped_column(String(10), default="1:3")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
