import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.observation import ClinicalObservation
from app.models.patient import Patient, Encounter
from app.models.agent import AuditLog
from app.schemas.observation import ObservationCreate, ObservationBatchCreate, ObservationCorrectionRequest
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

STANDARD_VITAL_TYPES = [
    "HEART_RATE", "BP_SYSTOLIC", "BP_DIASTOLIC", "SPO2",
    "TEMPERATURE_F", "RESPIRATORY_RATE", "PAIN_LEVEL", "GCS_SCORE", "BLOOD_GLUCOSE"
]


class ObservationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_observation(
        self,
        req: ObservationCreate,
        tenant_id: str,
        actor_id: str
    ) -> ClinicalObservation:
        """
        Record a single clinical observation with strict tenant isolation and audit logging.
        """
        # Verify patient ownership within tenant
        patient_stmt = select(Patient).where(and_(Patient.id == req.patient_id, Patient.tenant_id == tenant_id))
        patient = (await self.db.execute(patient_stmt)).scalars().first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient {req.patient_id} not found in tenant {tenant_id}"
            )

        # Verify encounter exists
        enc_stmt = select(Encounter).where(and_(Encounter.id == req.encounter_id, Encounter.patient_id == req.patient_id))
        encounter = (await self.db.execute(enc_stmt)).scalars().first()
        if not encounter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Encounter {req.encounter_id} not associated with patient {req.patient_id}"
            )

        obs = ClinicalObservation(
            id=f"OBS-{uuid.uuid4().hex[:8].upper()}",
            patient_id=req.patient_id,
            encounter_id=req.encounter_id,
            tenant_id=tenant_id,
            observation_type=req.observation_type.upper(),
            value_numeric=req.value_numeric,
            value_text=req.value_text,
            unit=req.unit,
            observed_at=req.observed_at or utc_now(),
            recorded_at=utc_now(),
            recorded_by=actor_id,
            source=req.source,
            status="ACTIVE",
            metadata_json=req.metadata_json or {}
        )
        self.db.add(obs)

        # Audit log entry
        audit = AuditLog(
            tenant_id=tenant_id,
            entity_type="clinical_observation",
            entity_id=obs.id,
            field_changed=obs.observation_type,
            old_value=None,
            new_value=str(obs.value_numeric if obs.value_numeric is not None else obs.value_text),
            changed_by=actor_id,
            change_reason=f"Clinical observation recorded from {req.source}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(obs)
        logger.info(f"Recorded observation {obs.id} ({obs.observation_type}) for patient {patient.id}")
        return obs

    async def record_batch(
        self,
        req: ObservationBatchCreate,
        tenant_id: str,
        actor_id: str
    ) -> List[ClinicalObservation]:
        """
        Bulk record multiple clinical observations (e.g. telemetry device monitor or lab feed).
        """
        patient_stmt = select(Patient).where(and_(Patient.id == req.patient_id, Patient.tenant_id == tenant_id))
        patient = (await self.db.execute(patient_stmt)).scalars().first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient {req.patient_id} not found in tenant {tenant_id}"
            )

        created_obs = []
        now = utc_now()
        for item in req.observations:
            obs = ClinicalObservation(
                id=f"OBS-{uuid.uuid4().hex[:8].upper()}",
                patient_id=req.patient_id,
                encounter_id=req.encounter_id,
                tenant_id=tenant_id,
                observation_type=str(item.get("observation_type", "NOTE")).upper(),
                value_numeric=item.get("value_numeric"),
                value_text=item.get("value_text"),
                unit=item.get("unit"),
                observed_at=item.get("observed_at") or now,
                recorded_at=now,
                recorded_by=actor_id,
                source=req.source,
                status="ACTIVE",
                metadata_json=item.get("metadata_json", {})
            )
            self.db.add(obs)
            created_obs.append(obs)

        await self.db.commit()
        for o in created_obs:
            await self.db.refresh(o)
        return created_obs

    async def get_patient_observations(
        self,
        patient_id: str,
        tenant_id: str,
        observation_type: Optional[str] = None,
        limit: int = 50,
        before_timestamp: Optional[datetime] = None
    ) -> List[ClinicalObservation]:
        """
        Query longitudinal clinical observations with cursor-based time windowing.
        """
        filters = [
            ClinicalObservation.patient_id == patient_id,
            ClinicalObservation.tenant_id == tenant_id,
            ClinicalObservation.status != "ENTERED_IN_ERROR"
        ]
        if observation_type:
            filters.append(ClinicalObservation.observation_type == observation_type.upper())
        if before_timestamp:
            filters.append(ClinicalObservation.observed_at < before_timestamp)

        stmt = (
            select(ClinicalObservation)
            .where(and_(*filters))
            .order_by(desc(ClinicalObservation.observed_at), desc(ClinicalObservation.id))
            .limit(min(limit, 100))
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_encounter_observations(
        self,
        encounter_id: str,
        tenant_id: str
    ) -> List[ClinicalObservation]:
        """
        Query all observations recorded during a specific encounter.
        """
        stmt = (
            select(ClinicalObservation)
            .where(and_(
                ClinicalObservation.encounter_id == encounter_id,
                ClinicalObservation.tenant_id == tenant_id,
                ClinicalObservation.status != "ENTERED_IN_ERROR"
            ))
            .order_by(desc(ClinicalObservation.observed_at))
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def correct_observation(
        self,
        observation_id: str,
        tenant_id: str,
        req: ObservationCorrectionRequest,
        actor_id: str
    ) -> ClinicalObservation:
        """
        Perform an append-only correction of a clinical measurement.
        The historical record is marked 'CORRECTED', and a new corrected observation is inserted
        linked back via `correction_of` to preserve full legal/audit integrity.
        """
        stmt = (
            select(ClinicalObservation)
            .where(and_(
                ClinicalObservation.id == observation_id,
                ClinicalObservation.tenant_id == tenant_id
            ))
            .with_for_update()
        )
        orig = (await self.db.execute(stmt)).scalars().first()
        if not orig:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Observation {observation_id} not found in tenant {tenant_id}"
            )

        orig.status = "CORRECTED"

        corrected_obs = ClinicalObservation(
            id=f"OBS-{uuid.uuid4().hex[:8].upper()}",
            patient_id=orig.patient_id,
            encounter_id=orig.encounter_id,
            tenant_id=tenant_id,
            observation_type=orig.observation_type,
            value_numeric=req.new_value_numeric if req.new_value_numeric is not None else orig.value_numeric,
            value_text=req.new_value_text if req.new_value_text is not None else orig.value_text,
            unit=req.new_unit or orig.unit,
            observed_at=orig.observed_at,
            recorded_at=utc_now(),
            recorded_by=actor_id,
            source="CORRECTION",
            status="ACTIVE",
            correction_of=orig.id,
            correction_reason=req.reason,
            metadata_json={"previous_value_numeric": orig.value_numeric, "previous_value_text": orig.value_text}
        )
        self.db.add(corrected_obs)

        # Audit log entry for legal compliance
        audit = AuditLog(
            tenant_id=tenant_id,
            entity_type="clinical_observation",
            entity_id=corrected_obs.id,
            field_changed=f"{orig.observation_type}_CORRECTION",
            old_value=str(orig.value_numeric if orig.value_numeric is not None else orig.value_text),
            new_value=str(corrected_obs.value_numeric if corrected_obs.value_numeric is not None else corrected_obs.value_text),
            changed_by=actor_id,
            change_reason=f"Correction of {orig.id}: {req.reason}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(corrected_obs)
        return corrected_obs

    async def get_latest_vitals(
        self,
        patient_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Returns the single most recent active measurement for each standard vital sign type.
        """
        vitals_map: Dict[str, Optional[ClinicalObservation]] = {v: None for v in STANDARD_VITAL_TYPES}
        last_updated: Optional[datetime] = None

        for vtype in STANDARD_VITAL_TYPES:
            stmt = (
                select(ClinicalObservation)
                .where(and_(
                    ClinicalObservation.patient_id == patient_id,
                    ClinicalObservation.tenant_id == tenant_id,
                    ClinicalObservation.observation_type == vtype,
                    ClinicalObservation.status == "ACTIVE"
                ))
                .order_by(desc(ClinicalObservation.observed_at))
                .limit(1)
            )
            obs = (await self.db.execute(stmt)).scalars().first()
            if obs:
                vitals_map[vtype] = obs
                if last_updated is None or obs.observed_at > last_updated:
                    last_updated = obs.observed_at

        return {
            "patient_id": patient_id,
            "tenant_id": tenant_id,
            "vitals": vitals_map,
            "last_updated": last_updated
        }
