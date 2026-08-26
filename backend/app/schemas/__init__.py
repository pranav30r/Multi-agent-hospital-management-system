from app.schemas.patient import PatientCreate, PatientResponse, EncounterCreate, EncounterResponse
from app.schemas.bed import BedResponse, BedManualBookRequest, BedStatusUpdate
from app.schemas.staff import StaffResponse, StaffStatusUpdate, StaffShiftResponse
from app.schemas.equipment import EquipmentResponse, EquipmentBookingCreate, EquipmentBookingResponse
from app.schemas.disease import DiseaseResponse, DiseaseCreate
from app.schemas.emergency import EmergencyDeclareRequest, EmergencyResponse, ApprovalItemResponse, ApprovalReviewRequest
from app.schemas.auth import TokenResponse, LoginRequest, StaffRegisterRequest

__all__ = [
    "PatientCreate", "PatientResponse", "EncounterCreate", "EncounterResponse",
    "BedResponse", "BedManualBookRequest", "BedStatusUpdate",
    "StaffResponse", "StaffStatusUpdate", "StaffShiftResponse",
    "EquipmentResponse", "EquipmentBookingCreate", "EquipmentBookingResponse",
    "DiseaseResponse", "DiseaseCreate",
    "EmergencyDeclareRequest", "EmergencyResponse", "ApprovalItemResponse", "ApprovalReviewRequest",
    "TokenResponse", "LoginRequest", "StaffRegisterRequest"
]
