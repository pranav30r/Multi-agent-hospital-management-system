import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.intake import ClinicalIntakeSession, IntakeQuestion, IntakeResponse
from app.models.patient import Patient, Encounter
from app.models.agent import AuditLog
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

VALID_INTERACTION_MODES = {"TEXT", "VOICE"}
VALID_INTAKE_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "REVIEWED"}
VALID_RESPONSE_TYPES = {"TEXT", "NUMBER", "BOOLEAN", "SINGLE_CHOICE", "MULTI_CHOICE", "SCALE"}


class ClinicalIntakeService:
    """
    Application Service for Clinical Intake Sessions, Question Sequencing, Response Ingestion,
    and Structured Medical History Generation for the Pre-Consultation Doctor Workflow.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 1. Session Lifecycle Operations ────────────────────────────────────

    async def start_intake_session(
        self,
        patient_id: str,
        encounter_id: Optional[str] = None,
        language: str = "en",
        interaction_mode: str = "TEXT",
        chief_complaint_raw: Optional[str] = None,
        custom_questions: Optional[List[Dict[str, Any]]] = None,
        actor_id: str = "SYSTEM"
    ) -> ClinicalIntakeSession:
        """
        Initialize a new Clinical Intake Session for a patient with foundational clinical questions.
        """
        # 1. Validate patient existence
        p_res = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        # 2. Validate encounter if provided
        if encounter_id:
            enc_res = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
            encounter = enc_res.scalars().first()
            if not encounter:
                raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
            if encounter.patient_id != patient_id:
                raise HTTPException(status_code=400, detail=f"Encounter {encounter_id} does not belong to patient {patient_id}")

        mode_clean = interaction_mode.upper()
        if mode_clean not in VALID_INTERACTION_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid interaction mode '{interaction_mode}'. Valid modes: {sorted(list(VALID_INTERACTION_MODES))}"
            )

        # 3. Create session record
        session = ClinicalIntakeSession(
            patient_id=patient_id,
            encounter_id=encounter_id,
            status="IN_PROGRESS",
            language=language.lower() if language else "en",
            interaction_mode=mode_clean,
            chief_complaint_raw=chief_complaint_raw or (encounter.chief_complaint if encounter_id and encounter else None),
            started_at=utc_now(),
            created_at=utc_now()
        )
        self.db.add(session)
        await self.db.flush()

        # 4. Populate questions
        questions_to_add = []
        if custom_questions:
            for idx, q_data in enumerate(custom_questions, start=1):
                q = IntakeQuestion(
                    session_id=session.id,
                    question_text=q_data["question_text"],
                    category=q_data.get("category", "SYMPTOMS").upper(),
                    order_index=q_data.get("order_index", idx),
                    is_required=q_data.get("is_required", True),
                    response_type=q_data.get("response_type", "TEXT").upper(),
                    allowed_options=q_data.get("allowed_options", []),
                    scale_min=q_data.get("scale_min", 1),
                    scale_max=q_data.get("scale_max", 10),
                    parent_question_id=q_data.get("parent_question_id"),
                    trigger_condition=q_data.get("trigger_condition"),
                    is_active=True
                )
                questions_to_add.append(q)
        else:
            # Default foundational clinical intake questionnaire
            q1 = IntakeQuestion(
                session_id=session.id,
                question_text="What is your primary health concern or reason for visit today?",
                category="CHIEF_COMPLAINT",
                order_index=1,
                is_required=True,
                response_type="TEXT"
            )
            q2 = IntakeQuestion(
                session_id=session.id,
                question_text="Please describe any specific symptoms you are experiencing.",
                category="SYMPTOMS",
                order_index=2,
                is_required=True,
                response_type="TEXT"
            )
            q3 = IntakeQuestion(
                session_id=session.id,
                question_text="Are you currently experiencing any physical pain?",
                category="PAIN_PRESENCE",
                order_index=3,
                is_required=True,
                response_type="BOOLEAN"
            )
            self.db.add_all([q1, q2, q3])
            await self.db.flush()

            # Conditional pain questions linked to Q3
            q4 = IntakeQuestion(
                session_id=session.id,
                question_text="Where is the pain located?",
                category="LOCATION",
                order_index=4,
                is_required=False,
                response_type="TEXT",
                parent_question_id=q3.id,
                trigger_condition={"parent_value": True}
            )
            q5 = IntakeQuestion(
                session_id=session.id,
                question_text="On a scale from 1 to 10, how would you rate the severity of your pain?",
                category="SEVERITY",
                order_index=5,
                is_required=False,
                response_type="SCALE",
                scale_min=1,
                scale_max=10,
                parent_question_id=q3.id,
                trigger_condition={"parent_value": True}
            )
            q6 = IntakeQuestion(
                session_id=session.id,
                question_text="How long have you been experiencing these symptoms (e.g., hours, days)?",
                category="DURATION",
                order_index=6,
                is_required=True,
                response_type="TEXT"
            )
            q7 = IntakeQuestion(
                session_id=session.id,
                question_text="Are you currently taking any prescription or regular medications?",
                category="MEDICATIONS",
                order_index=7,
                is_required=False,
                response_type="TEXT"
            )
            q8 = IntakeQuestion(
                session_id=session.id,
                question_text="Do you have any known drug or environmental allergies?",
                category="ALLERGIES",
                order_index=8,
                is_required=False,
                response_type="TEXT"
            )
            q9 = IntakeQuestion(
                session_id=session.id,
                question_text="Do you have any significant past medical conditions (such as diabetes, hypertension, asthma)?",
                category="PAST_HISTORY",
                order_index=9,
                is_required=False,
                response_type="TEXT"
            )
            questions_to_add.extend([q4, q5, q6, q7, q8, q9])

        if questions_to_add:
            self.db.add_all(questions_to_add)
            await self.db.flush()

        # Update total questions count
        q_count_res = await self.db.execute(
            select(IntakeQuestion).where(IntakeQuestion.session_id == session.id)
        )
        all_questions = q_count_res.scalars().all()
        session.total_questions = len(all_questions)
        session.answered_questions = 0
        session.completion_percentage = 0.0

        audit = AuditLog(
            entity_type="clinical_intake",
            entity_id=session.id,
            field_changed="session_started",
            old_value=None,
            new_value="IN_PROGRESS",
            changed_by=actor_id,
            change_reason=f"Started clinical intake for patient {patient_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Clinical intake session {session.id} started for patient {patient_id} ({session.total_questions} questions)")
        return session

    async def get_intake_session(self, session_id: str) -> Optional[ClinicalIntakeSession]:
        """Fetch clinical intake session by primary key ID."""
        stmt = (
            select(ClinicalIntakeSession)
            .options(
                selectinload(ClinicalIntakeSession.questions),
                selectinload(ClinicalIntakeSession.responses)
            )
            .where(ClinicalIntakeSession.id == session_id)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # ─── 2. Question Sequencing & Retrieval ─────────────────────────────────

    async def get_current_question(self, session_id: str) -> Optional[IntakeQuestion]:
        """
        Determine and return the next active unanswered question in the intake sequence.
        Evaluates conditional triggers based on prior responses.
        """
        session = await self.get_intake_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")

        if session.status in ["COMPLETED", "REVIEWED"]:
            return None

        # Fetch all questions ordered by order_index
        q_stmt = (
            select(IntakeQuestion)
            .where(IntakeQuestion.session_id == session_id)
            .order_by(IntakeQuestion.order_index)
        )
        q_res = await self.db.execute(q_stmt)
        questions = q_res.scalars().all()

        for q in questions:
            if q.is_answered or q.is_skipped or not q.is_active:
                continue

            # Check if this question is conditional upon a parent question
            if q.parent_question_id and q.trigger_condition:
                parent_resp_stmt = select(IntakeResponse).where(
                    IntakeResponse.session_id == session_id,
                    IntakeResponse.question_id == q.parent_question_id
                )
                p_resp_res = await self.db.execute(parent_resp_stmt)
                parent_resp = p_resp_res.scalars().first()

                if not parent_resp:
                    # Parent hasn't been answered yet, wait
                    continue

                # Check if condition is satisfied
                target_val = q.trigger_condition.get("parent_value")
                parent_val = parent_resp.structured_value.get("value") if parent_resp.structured_value else parent_resp.raw_response

                is_triggered = False
                if isinstance(target_val, bool):
                    is_triggered = bool(parent_val is True or str(parent_val).lower() in ["true", "yes", "1"])
                elif target_val is not None:
                    is_triggered = str(parent_val).strip().lower() == str(target_val).strip().lower()

                if not is_triggered:
                    # Condition not met, deactivate question and continue to next
                    q.is_active = False
                    q.is_skipped = True
                    await self.db.commit()
                    continue

            return q

        return None

    # ─── 3. Response Ingestion & Validation ─────────────────────────────────

    async def submit_response(
        self,
        session_id: str,
        question_id: str,
        raw_response: str,
        structured_value: Optional[Dict[str, Any]] = None,
        actor_id: str = "PATIENT"
    ) -> IntakeResponse:
        """
        Validate and ingest a patient response, update question status, and recompute completion telemetry.
        """
        result = await self.db.execute(
            select(ClinicalIntakeSession).where(ClinicalIntakeSession.id == session_id).with_for_update()
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")

        if session.status in ["COMPLETED", "REVIEWED"]:
            raise HTTPException(status_code=400, detail=f"Cannot submit response to an already {session.status} intake session")

        # Fetch question with lock
        q_result = await self.db.execute(
            select(IntakeQuestion).where(
                IntakeQuestion.id == question_id,
                IntakeQuestion.session_id == session_id
            ).with_for_update()
        )
        question = q_result.scalars().first()
        if not question:
            raise HTTPException(status_code=404, detail=f"Question {question_id} not found in session {session_id}")

        if question.is_answered:
            raise HTTPException(status_code=400, detail=f"Question {question_id} has already been answered")

        raw_clean = str(raw_response).strip()
        if not raw_clean and question.is_required:
            raise HTTPException(status_code=400, detail="Response cannot be empty for a required question")

        # Validate by response type
        parsed_structured = structured_value or {}
        r_type = question.response_type.upper()

        if r_type == "SCALE":
            try:
                val = int(raw_clean)
                s_min = question.scale_min if question.scale_min is not None else 1
                s_max = question.scale_max if question.scale_max is not None else 10
                if not (s_min <= val <= s_max):
                    raise ValueError()
                parsed_structured.setdefault("value", val)
                parsed_structured.setdefault("scale_range", f"{s_min}-{s_max}")
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Scale response must be an integer between {question.scale_min or 1} and {question.scale_max or 10}"
                )

        elif r_type == "BOOLEAN":
            lower_val = raw_clean.lower()
            if lower_val in ["true", "yes", "y", "1"]:
                bool_val = True
            elif lower_val in ["false", "no", "n", "0"]:
                bool_val = False
            else:
                raise HTTPException(status_code=400, detail="Boolean response must be True/False or Yes/No")
            parsed_structured.setdefault("value", bool_val)

        elif r_type == "NUMBER":
            try:
                num_val = float(raw_clean) if "." in raw_clean else int(raw_clean)
                parsed_structured.setdefault("value", num_val)
            except ValueError:
                raise HTTPException(status_code=400, detail="Response must be a valid number")

        elif r_type == "SINGLE_CHOICE":
            options = question.allowed_options or []
            if options and raw_clean.upper() not in [str(opt).upper() for opt in options]:
                raise HTTPException(status_code=400, detail=f"Response must be one of allowed options: {options}")
            parsed_structured.setdefault("value", raw_clean)

        else:  # TEXT
            if len(raw_clean) > 2000:
                raise HTTPException(status_code=400, detail="Text response exceeds maximum allowed length of 2000 characters")
            parsed_structured.setdefault("value", raw_clean)

        # Create response record
        response = IntakeResponse(
            session_id=session_id,
            question_id=question_id,
            patient_id=session.patient_id,
            raw_response=raw_clean,
            structured_value=parsed_structured,
            response_type=r_type,
            recorded_at=utc_now()
        )
        self.db.add(response)

        # Mark question answered
        question.is_answered = True
        question.is_skipped = False

        # Recompute session telemetry
        q_all_res = await self.db.execute(
            select(IntakeQuestion).where(IntakeQuestion.session_id == session_id, IntakeQuestion.is_active == True)
        )
        active_questions = q_all_res.scalars().all()
        answered_count = sum(1 for q in active_questions if q.is_answered)
        
        session.answered_questions = answered_count
        session.total_questions = len(active_questions)
        session.completion_percentage = round((answered_count / max(len(active_questions), 1)) * 100, 1)

        audit = AuditLog(
            entity_type="clinical_intake",
            entity_id=session_id,
            field_changed="question_answered",
            old_value=None,
            new_value=question.category,
            changed_by=actor_id,
            change_reason=f"Answered intake question {question_id} ({question.category})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(response)
        return response

    async def skip_question(
        self,
        session_id: str,
        question_id: str,
        actor_id: str = "PATIENT"
    ) -> IntakeQuestion:
        """
        Skip an optional question in the intake sequence.
        """
        result = await self.db.execute(
            select(ClinicalIntakeSession).where(ClinicalIntakeSession.id == session_id).with_for_update()
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")

        if session.status in ["COMPLETED", "REVIEWED"]:
            raise HTTPException(status_code=400, detail=f"Cannot skip question on an already {session.status} intake session")

        q_result = await self.db.execute(
            select(IntakeQuestion).where(
                IntakeQuestion.id == question_id,
                IntakeQuestion.session_id == session_id
            ).with_for_update()
        )
        question = q_result.scalars().first()
        if not question:
            raise HTTPException(status_code=404, detail=f"Question {question_id} not found")

        if question.is_required:
            raise HTTPException(status_code=400, detail=f"Cannot skip required question '{question.question_text}'")

        question.is_skipped = True
        question.is_answered = False

        audit = AuditLog(
            entity_type="clinical_intake",
            entity_id=session_id,
            field_changed="question_skipped",
            old_value=None,
            new_value=question.category,
            changed_by=actor_id,
            change_reason=f"Skipped optional intake question {question_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(question)
        return question

    # ─── 4. Intake Completion & Structured History Generation ───────────────

    async def complete_intake_session(
        self,
        session_id: str,
        actor_id: str = "PATIENT"
    ) -> ClinicalIntakeSession:
        """
        Complete the intake session once all active required questions are answered,
        and synthesize a structured clinical summary.
        """
        result = await self.db.execute(
            select(ClinicalIntakeSession).where(ClinicalIntakeSession.id == session_id).with_for_update()
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")

        if session.status in ["COMPLETED", "REVIEWED"]:
            return session

        # Verify no active required questions remain unanswered
        q_res = await self.db.execute(
            select(IntakeQuestion).where(
                IntakeQuestion.session_id == session_id,
                IntakeQuestion.is_active == True,
                IntakeQuestion.is_required == True,
                IntakeQuestion.is_answered == False
            )
        )
        unanswered_required = q_res.scalars().all()
        if unanswered_required:
            categories = [q.category for q in unanswered_required]
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete intake: {len(unanswered_required)} required question(s) remain unanswered: {categories}"
            )

        # Retrieve all responses for aggregation
        r_res = await self.db.execute(
            select(IntakeResponse, IntakeQuestion)
            .join(IntakeQuestion, IntakeResponse.question_id == IntakeQuestion.id)
            .where(IntakeResponse.session_id == session_id)
            .order_by(IntakeQuestion.order_index)
        )
        response_rows = r_res.all()

        structured: Dict[str, Any] = {
            "chief_complaint": None,
            "symptoms": [],
            "pain": {"present": False, "location": None, "score": None},
            "duration": None,
            "medications": None,
            "allergies": None,
            "past_medical_history": None,
            "raw_qa_trail": []
        }

        for resp, q in response_rows:
            cat = q.category.upper()
            val = resp.structured_value.get("value") if resp.structured_value else resp.raw_response

            structured["raw_qa_trail"].append({
                "question_id": q.id,
                "category": cat,
                "question": q.question_text,
                "response": resp.raw_response,
                "structured": resp.structured_value
            })

            if cat == "CHIEF_COMPLAINT":
                structured["chief_complaint"] = resp.raw_response
            elif cat == "SYMPTOMS":
                structured["symptoms"].append(resp.raw_response)
            elif cat == "PAIN_PRESENCE":
                structured["pain"]["present"] = bool(val is True or str(val).lower() in ["true", "yes"])
            elif cat == "LOCATION":
                structured["pain"]["location"] = resp.raw_response
            elif cat == "SEVERITY":
                structured["pain"]["score"] = val
            elif cat == "DURATION":
                structured["duration"] = resp.raw_response
            elif cat == "MEDICATIONS":
                structured["medications"] = resp.raw_response
            elif cat == "ALLERGIES":
                structured["allergies"] = resp.raw_response
            elif cat == "PAST_HISTORY":
                structured["past_medical_history"] = resp.raw_response

        session.status = "COMPLETED"
        session.completed_at = utc_now()
        session.completion_percentage = 100.0
        session.structured_summary = structured

        audit = AuditLog(
            entity_type="clinical_intake",
            entity_id=session_id,
            field_changed="session_completed",
            old_value="IN_PROGRESS",
            new_value="COMPLETED",
            changed_by=actor_id,
            change_reason="Completed patient clinical intake questionnaire"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Clinical intake session {session_id} marked COMPLETED (100% finished)")
        return session

    async def review_intake_session(
        self,
        session_id: str,
        reviewer_id: str,
        notes: Optional[str] = None
    ) -> ClinicalIntakeSession:
        """
        Mark a completed clinical intake as reviewed by a physician.
        """
        result = await self.db.execute(
            select(ClinicalIntakeSession).where(ClinicalIntakeSession.id == session_id).with_for_update()
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")

        if session.status != "COMPLETED":
            raise HTTPException(status_code=400, detail=f"Cannot review an intake session in '{session.status}' state. Must be COMPLETED.")

        session.status = "REVIEWED"
        session.reviewed_at = utc_now()
        session.reviewed_by = reviewer_id

        audit = AuditLog(
            entity_type="clinical_intake",
            entity_id=session_id,
            field_changed="session_reviewed",
            old_value="COMPLETED",
            new_value="REVIEWED",
            changed_by=reviewer_id,
            change_reason=notes or "Physician clinical intake review"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(session)
        return session

    # ─── 5. Structured Doctor Retrieval ─────────────────────────────────────

    async def get_structured_intake(self, session_id: str) -> Dict[str, Any]:
        """
        Format comprehensive structured clinical intake record for doctor consultation.
        """
        session = await self.get_intake_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")

        p_res = await self.db.execute(select(Patient).where(Patient.id == session.patient_id))
        patient = p_res.scalars().first()

        encounter_data = None
        if session.encounter_id:
            enc_res = await self.db.execute(select(Encounter).where(Encounter.id == session.encounter_id))
            encounter = enc_res.scalars().first()
            if encounter:
                encounter_data = {
                    "id": encounter.id,
                    "encounter_type": encounter.encounter_type,
                    "department_id": encounter.current_department_id,
                    "esi_level": encounter.esi_level,
                    "patient_status": encounter.patient_status
                }

        return {
            "session_id": session.id,
            "status": session.status,
            "language": session.language,
            "interaction_mode": session.interaction_mode,
            "completion_percentage": session.completion_percentage,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "reviewed_at": session.reviewed_at,
            "reviewed_by": session.reviewed_by,
            "patient": {
                "id": patient.id if patient else session.patient_id,
                "name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
                "age": patient.age if patient else None,
                "gender": patient.gender if patient else None,
                "blood_group": patient.blood_group if patient else None
            },
            "encounter": encounter_data,
            "structured_summary": session.structured_summary or {},
            "total_questions": session.total_questions,
            "answered_questions": session.answered_questions
        }

    async def get_intake_by_encounter(self, encounter_id: str) -> Optional[ClinicalIntakeSession]:
        """Fetch the clinical intake session associated with a specific encounter."""
        stmt = (
            select(ClinicalIntakeSession)
            .options(
                selectinload(ClinicalIntakeSession.questions),
                selectinload(ClinicalIntakeSession.responses)
            )
            .where(ClinicalIntakeSession.encounter_id == encounter_id)
            .order_by(ClinicalIntakeSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_doctor_clinical_view(self, encounter_id: str) -> Dict[str, Any]:
        """
        Assemble consolidated clinical pre-consultation view for the attending doctor:
        Patient Demographics + Current Encounter Vitals + Completed Clinical Intake + Medical History + Prior Visits.
        """
        enc_res = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        p_res = await self.db.execute(select(Patient).where(Patient.id == encounter.patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {encounter.patient_id} not found")

        # Fetch associated intake session
        intake_session = await self.get_intake_by_encounter(encounter_id)
        if not intake_session:
            # Fallback: check most recent completed intake for this patient
            recent_res = await self.db.execute(
                select(ClinicalIntakeSession)
                .options(
                    selectinload(ClinicalIntakeSession.questions),
                    selectinload(ClinicalIntakeSession.responses)
                )
                .where(
                    ClinicalIntakeSession.patient_id == patient.id,
                    ClinicalIntakeSession.status.in_(["COMPLETED", "REVIEWED"])
                )
                .order_by(ClinicalIntakeSession.created_at.desc())
            )
            intake_session = recent_res.scalars().first()

        # Prior encounters for longitudinal context
        prior_res = await self.db.execute(
            select(Encounter)
            .where(Encounter.patient_id == patient.id, Encounter.id != encounter_id)
            .order_by(Encounter.arrival_time.desc())
        )
        prior_encounters = prior_res.scalars().all()

        # Documents associated with encounter / patient
        from app.models.clinical_document import ClinicalDocument, ClinicalInvestigation

        doc_res = await self.db.execute(
            select(ClinicalDocument)
            .where(ClinicalDocument.encounter_id == encounter_id)
            .order_by(ClinicalDocument.created_at.desc())
        )
        documents = [
            {
                "id": d.id,
                "document_type": d.document_type,
                "title": d.title,
                "status": d.status,
                "storage_key": d.storage_key,
                "storage_provider": d.storage_provider,
                "is_verified": d.is_verified,
                "verified_by": d.verified_by,
                "document_date": d.document_date.isoformat() if d.document_date else None,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in doc_res.scalars().all()
        ]

        # Investigations associated with encounter
        inv_res = await self.db.execute(
            select(ClinicalInvestigation)
            .where(ClinicalInvestigation.encounter_id == encounter_id)
            .order_by(ClinicalInvestigation.ordered_at.desc())
        )
        investigations = [
            {
                "id": inv.id,
                "investigation_type": inv.investigation_type,
                "test_name": inv.test_name,
                "status": inv.status,
                "result_summary": inv.result_summary,
                "result_values": inv.result_values,
                "is_abnormal": inv.is_abnormal,
                "abnormal_flags": inv.abnormal_flags or [],
                "is_verified": inv.is_verified,
                "verified_by": inv.verified_by,
                "document_id": inv.document_id,
                "ordered_at": inv.ordered_at.isoformat() if inv.ordered_at else None,
                "completed_at": inv.completed_at.isoformat() if inv.completed_at else None
            }
            for inv in inv_res.scalars().all()
        ]

        # Clinical Priority Recommendation
        from app.models.priority import ClinicalPriorityRecommendation

        pri_res = await self.db.execute(
            select(ClinicalPriorityRecommendation)
            .where(ClinicalPriorityRecommendation.encounter_id == encounter_id)
            .order_by(ClinicalPriorityRecommendation.created_at.desc())
        )
        priority_rec = pri_res.scalars().first()
        priority_data = None
        if priority_rec:
            priority_data = {
                "id": priority_rec.id,
                "priority_level": priority_rec.priority_level,
                "route": priority_rec.route,
                "score": priority_rec.score,
                "requires_priority_attention": priority_rec.requires_priority_attention,
                "status": priority_rec.status,
                "reasons": priority_rec.reasons or [],
                "red_flags": priority_rec.red_flags or [],
                "missing_information": priority_rec.missing_information or [],
                "acknowledged_by": priority_rec.acknowledged_by,
                "overridden_by": priority_rec.overridden_by,
                "override_priority_level": priority_rec.override_priority_level,
                "override_route": priority_rec.override_route,
                "override_reason": priority_rec.override_reason
            }

        return {
            "encounter_id": encounter.id,
            "doctor_ready": bool(intake_session and intake_session.status in ["COMPLETED", "REVIEWED"]),
            "intake_status": intake_session.status if intake_session else "NOT_STARTED",
            "patient": {
                "id": patient.id,
                "name": f"{patient.first_name} {patient.last_name}",
                "age": patient.age,
                "gender": patient.gender,
                "blood_group": patient.blood_group,
                "contact_phone": patient.contact_phone,
                "emergency_contact": patient.emergency_contact,
                "allergies": patient.allergies or [],
                "chronic_conditions": patient.chronic_conditions or []
            },
            "current_encounter": {
                "id": encounter.id,
                "encounter_type": encounter.encounter_type,
                "current_department_id": encounter.current_department_id,
                "current_bed_id": encounter.current_bed_id,
                "assigned_doctor_id": encounter.assigned_doctor_id,
                "assigned_nurse_id": encounter.assigned_nurse_id,
                "esi_level": encounter.esi_level,
                "priority": encounter.priority,
                "patient_status": encounter.patient_status,
                "chief_complaint": encounter.chief_complaint,
                "vitals": {
                    "heart_rate": encounter.heart_rate,
                    "bp_systolic": encounter.bp_systolic,
                    "bp_diastolic": encounter.bp_diastolic,
                    "spo2": encounter.spo2,
                    "temperature_f": encounter.temperature_f,
                    "pain_level": encounter.pain_level,
                    "respiratory_rate": encounter.respiratory_rate,
                    "gcs_score": encounter.gcs_score
                },
                "diagnosed_diseases": encounter.diagnosed_diseases or [],
                "diagnosis_notes": encounter.diagnosis_notes,
                "arrival_time": encounter.arrival_time,
                "triage_time": encounter.triage_time,
                "doctor_assigned_time": encounter.doctor_assigned_time
            },
            "clinical_intake": {
                "session_id": intake_session.id if intake_session else None,
                "status": intake_session.status if intake_session else "NOT_STARTED",
                "language": intake_session.language if intake_session else "en",
                "interaction_mode": intake_session.interaction_mode if intake_session else "TEXT",
                "completion_percentage": intake_session.completion_percentage if intake_session else 0.0,
                "completed_at": intake_session.completed_at if intake_session else None,
                "reviewed_at": intake_session.reviewed_at if intake_session else None,
                "reviewed_by": intake_session.reviewed_by if intake_session else None,
                "structured_summary": intake_session.structured_summary if intake_session else {}
            },
            "clinical_priority": priority_data,
            "documents": documents,
            "investigations": investigations,
            "previous_encounters": [
                {
                    "id": pe.id,
                    "encounter_type": pe.encounter_type,
                    "department_id": pe.current_department_id,
                    "arrival_time": pe.arrival_time,
                    "discharge_time": pe.discharge_time,
                    "status": pe.status,
                    "chief_complaint": pe.chief_complaint,
                    "diagnosis_notes": pe.diagnosis_notes
                }
                for pe in prior_encounters
            ]
        }

    async def get_patient_timeline(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Generate a unified chronological medical timeline for a patient across all encounters,
        clinical intake sessions, clinical documents, investigations, and priority decisions.
        """
        from app.models.clinical_document import ClinicalDocument, ClinicalInvestigation
        from app.models.priority import ClinicalPriorityRecommendation

        p_res = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        events: List[Dict[str, Any]] = []

        # 1. Encounter Events
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.patient_id == patient_id)
        )
        encounters = enc_res.scalars().all()
        for enc in encounters:
            if enc.arrival_time:
                events.append({
                    "event_type": "ENCOUNTER_ARRIVED",
                    "event_title": f"Hospital Arrival ({enc.encounter_type})",
                    "timestamp": enc.arrival_time,
                    "encounter_id": enc.id,
                    "department_id": enc.current_department_id,
                    "details": {"chief_complaint": enc.chief_complaint, "patient_status": enc.patient_status}
                })
            if enc.triage_time:
                events.append({
                    "event_type": "TRIAGE_COMPLETED",
                    "event_title": f"Triage Assessment (ESI {enc.esi_level})",
                    "timestamp": enc.triage_time,
                    "encounter_id": enc.id,
                    "department_id": enc.current_department_id,
                    "details": {
                        "esi_level": enc.esi_level,
                        "heart_rate": enc.heart_rate,
                        "bp": f"{enc.bp_systolic}/{enc.bp_diastolic}" if enc.bp_systolic else None,
                        "spo2": enc.spo2,
                        "temperature_f": enc.temperature_f,
                        "pain_level": enc.pain_level
                    }
                })
            if enc.doctor_assigned_time:
                events.append({
                    "event_type": "DOCTOR_ASSIGNED",
                    "event_title": f"Doctor Assigned ({enc.assigned_doctor_id})",
                    "timestamp": enc.doctor_assigned_time,
                    "encounter_id": enc.id,
                    "department_id": enc.current_department_id,
                    "details": {"assigned_doctor_id": enc.assigned_doctor_id}
                })
            if enc.discharge_time:
                events.append({
                    "event_type": "PATIENT_DISCHARGED",
                    "event_title": "Patient Discharged",
                    "timestamp": enc.discharge_time,
                    "encounter_id": enc.id,
                    "department_id": enc.current_department_id,
                    "details": {"status": enc.status, "diagnosis_notes": enc.diagnosis_notes}
                })

        # 2. Intake Session Events
        intk_res = await self.db.execute(
            select(ClinicalIntakeSession).where(ClinicalIntakeSession.patient_id == patient_id)
        )
        intakes = intk_res.scalars().all()
        for intk in intakes:
            if intk.started_at:
                events.append({
                    "event_type": "INTAKE_STARTED",
                    "event_title": f"Clinical Intake Started ({intk.interaction_mode})",
                    "timestamp": intk.started_at,
                    "session_id": intk.id,
                    "encounter_id": intk.encounter_id,
                    "details": {"language": intk.language, "chief_complaint_raw": intk.chief_complaint_raw}
                })
            if intk.completed_at:
                events.append({
                    "event_type": "INTAKE_COMPLETED",
                    "event_title": "Clinical Intake Questionnaire Completed",
                    "timestamp": intk.completed_at,
                    "session_id": intk.id,
                    "encounter_id": intk.encounter_id,
                    "details": {
                        "structured_summary": intk.structured_summary,
                        "answered_questions": intk.answered_questions
                    }
                })
            if intk.reviewed_at:
                events.append({
                    "event_type": "INTAKE_REVIEWED",
                    "event_title": f"Clinical Intake Reviewed by Doctor ({intk.reviewed_by})",
                    "timestamp": intk.reviewed_at,
                    "session_id": intk.id,
                    "encounter_id": intk.encounter_id,
                    "details": {"reviewed_by": intk.reviewed_by}
                })

        # 3. Clinical Document Events
        doc_res = await self.db.execute(
            select(ClinicalDocument).where(ClinicalDocument.patient_id == patient_id)
        )
        for doc in doc_res.scalars().all():
            if doc.created_at:
                events.append({
                    "event_type": "DOCUMENT_RECORDED",
                    "event_title": f"Clinical Document Recorded: {doc.title} ({doc.document_type})",
                    "timestamp": doc.created_at,
                    "document_id": doc.id,
                    "encounter_id": doc.encounter_id,
                    "details": {"document_type": doc.document_type, "title": doc.title, "storage_key": doc.storage_key}
                })
            if doc.is_verified and doc.verified_at:
                events.append({
                    "event_type": "DOCUMENT_VERIFIED",
                    "event_title": f"Clinical Document Verified ({doc.title})",
                    "timestamp": doc.verified_at,
                    "document_id": doc.id,
                    "encounter_id": doc.encounter_id,
                    "details": {"verified_by": doc.verified_by}
                })

        # 4. Clinical Investigation Events
        inv_res = await self.db.execute(
            select(ClinicalInvestigation).where(ClinicalInvestigation.patient_id == patient_id)
        )
        for inv in inv_res.scalars().all():
            if inv.ordered_at:
                events.append({
                    "event_type": "INVESTIGATION_ORDERED",
                    "event_title": f"Investigation Ordered: {inv.test_name} ({inv.investigation_type})",
                    "timestamp": inv.ordered_at,
                    "investigation_id": inv.id,
                    "encounter_id": inv.encounter_id,
                    "details": {"test_name": inv.test_name, "investigation_type": inv.investigation_type}
                })
            if inv.completed_at:
                events.append({
                    "event_type": "INVESTIGATION_COMPLETED",
                    "event_title": f"Investigation Results Completed: {inv.test_name}" + (" [ABNORMAL]" if inv.is_abnormal else ""),
                    "timestamp": inv.completed_at,
                    "investigation_id": inv.id,
                    "encounter_id": inv.encounter_id,
                    "details": {
                        "test_name": inv.test_name,
                        "is_abnormal": inv.is_abnormal,
                        "result_summary": inv.result_summary,
                        "abnormal_flags": inv.abnormal_flags
                    }
                })
            if inv.is_verified and inv.verified_at:
                events.append({
                    "event_type": "INVESTIGATION_VERIFIED",
                    "event_title": f"Investigation Verified: {inv.test_name} by {inv.verified_by}",
                    "timestamp": inv.verified_at,
                    "investigation_id": inv.id,
                    "encounter_id": inv.encounter_id,
                    "details": {"verified_by": inv.verified_by}
                })

        # 5. Clinical Priority Events
        pri_res = await self.db.execute(
            select(ClinicalPriorityRecommendation).where(ClinicalPriorityRecommendation.patient_id == patient_id)
        )
        for pri in pri_res.scalars().all():
            if pri.created_at:
                events.append({
                    "event_type": "PRIORITY_ASSESSMENT_GENERATED",
                    "event_title": f"Clinical Priority Classified: {pri.priority_level} -> {pri.route}",
                    "timestamp": pri.created_at,
                    "recommendation_id": pri.id,
                    "encounter_id": pri.encounter_id,
                    "details": {"priority_level": pri.priority_level, "route": pri.route, "score": pri.score}
                })
            if pri.acknowledged_at:
                events.append({
                    "event_type": "PRIORITY_ACKNOWLEDGED",
                    "event_title": f"Priority Recommendation Acknowledged ({pri.priority_level})",
                    "timestamp": pri.acknowledged_at,
                    "recommendation_id": pri.id,
                    "encounter_id": pri.encounter_id,
                    "details": {"acknowledged_by": pri.acknowledged_by, "notes": pri.acknowledgement_notes}
                })
            if pri.overridden_at:
                events.append({
                    "event_type": "PRIORITY_OVERRIDDEN",
                    "event_title": f"Priority Overridden: {pri.override_priority_level} by {pri.overridden_by}",
                    "timestamp": pri.overridden_at,
                    "recommendation_id": pri.id,
                    "encounter_id": pri.encounter_id,
                    "details": {
                        "override_priority_level": pri.override_priority_level,
                        "override_route": pri.override_route,
                        "override_reason": pri.override_reason
                    }
                })

        # Sort all events chronologically in descending order (newest first)
        events.sort(key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min, reverse=True)
        return events

    async def list_patient_intakes(self, patient_id: str) -> List[ClinicalIntakeSession]:
        """List all clinical intake sessions recorded for a patient."""
        stmt = (
            select(ClinicalIntakeSession)
            .where(ClinicalIntakeSession.patient_id == patient_id)
            .order_by(ClinicalIntakeSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
