"""Peer evaluation service: handles submission, retrieval, and access control
for student peer evaluations within project groups.
"""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import fmean, stdev
from uuid import uuid4

from fastapi import HTTPException, status

from app.repositories.interfaces import (
    PeerEvaluationConfigRecord,
    PeerEvaluationRecord,
    PeerEvaluationRepository,
    ProjectRepository,
    UserRepository,
)
from app.schemas.auth import Role
from app.schemas.peer_evaluation import (
    MemberPeerEvaluationDetail,
    PeerEvaluationConfigCreate,
    PeerEvaluationConfigResponse,
    PeerEvaluationCreate,
    PeerEvaluationInstructorView,
    PeerEvaluationReceivedItem,
    PeerEvaluationResponse,
    PeerEvaluationSummary,
    PeerEvaluationUpdate,
)
from app.services.auditLogService.service import append_action_audit

# Flag totals/scores at least one sample standard deviation from the mean.
OUTLIER_Z_THRESHOLD = 1.0


def _mean_and_sample_stdev(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = fmean(values)
    sample_stdev = stdev(values) if len(values) >= 2 else None
    return mean, sample_stdev


def _z_score(value: float, mean: float | None, sample_stdev: float | None) -> float | None:
    if mean is None or sample_stdev is None or sample_stdev == 0:
        return None
    return (value - mean) / sample_stdev


def _is_outlier(z: float | None) -> bool:
    return z is not None and abs(z) >= OUTLIER_Z_THRESHOLD


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


class PeerEvaluationService:
    def __init__(
        self,
        peer_evaluation_repository: PeerEvaluationRepository,
        project_repository: ProjectRepository,
        user_repository: UserRepository,
        action_audits,
    ) -> None:
        self._peer_evaluation_repository = peer_evaluation_repository
        self._project_repository = project_repository
        self._user_repository = user_repository
        self._action_audits = action_audits

    # ------------------------------------------------------------------
    # Configuration (instructor only)
    # ------------------------------------------------------------------

    def set_evaluation_config(
        self,
        course_id: str,
        payload: PeerEvaluationConfigCreate,
        current_user_id: str,
    ) -> PeerEvaluationConfigResponse:
        """Open or close peer evaluation for a course and set an expiry date."""
        config = PeerEvaluationConfigRecord(
            course_id=course_id,
            is_open=payload.is_open,
            opens_at=payload.opens_at,
            expires_at=payload.expires_at,
            updated_by=current_user_id,
            updated_at=datetime.now(UTC),
        )
        saved = self._peer_evaluation_repository.save_config(config)

        append_action_audit(
            self._action_audits,
            actor_id=current_user_id,
            actor_role=Role.INSTRUCTOR.value,
            action="set_peer_evaluation_config",
            target_type="course",
            target_id=course_id,
            details={
                "is_open": payload.is_open,
                "expires_at": payload.expires_at.isoformat()
                if payload.expires_at
                else None,
            },
        )

        return PeerEvaluationConfigResponse(
            course_id=saved.course_id,
            is_open=saved.is_open,
            opens_at=saved.opens_at,
            expires_at=saved.expires_at,
            updated_by=saved.updated_by,
            updated_at=saved.updated_at,
        )

    def get_evaluation_config(
        self, course_id: str
    ) -> PeerEvaluationConfigResponse | None:
        config = self._peer_evaluation_repository.get_config(course_id)
        if config is None:
            return None
        return PeerEvaluationConfigResponse(
            course_id=config.course_id,
            is_open=config.is_open,
            opens_at=config.opens_at,
            expires_at=config.expires_at,
            updated_by=config.updated_by,
            updated_at=config.updated_at,
        )

    def _check_evaluation_window(self, course_id: str) -> None:
        """Raise if peer evaluation is not currently open for the course.

        An evaluation is open when:
        - config.is_open is True, AND
        - opens_at is None OR now >= opens_at, AND
        - expires_at is None OR now <= expires_at
        """
        config = self._peer_evaluation_repository.get_config(course_id)
        if config is None or not config.is_open:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Peer evaluation is not currently open for this course.",
            )
        now = datetime.now(UTC)
        if config.opens_at is not None and now < config.opens_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Peer evaluation opens at {config.opens_at.isoformat()}.",
            )
        if config.expires_at is not None and now > config.expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Peer evaluation has expired for this course.",
            )

    # ------------------------------------------------------------------
    # Student submission
    # ------------------------------------------------------------------

    def submit_evaluation(
        self,
        payload: PeerEvaluationCreate,
        rater_id: str,
    ) -> tuple[PeerEvaluationResponse, bool]:
        """Student submits an evaluation of a group member.

        Returns (response, is_update) where is_update indicates whether
        an existing evaluation was overwritten.

        - Rater must be a member of the project.
        - Rated student must be a member of the same project.
        - A student cannot evaluate themselves.
        - Evaluation window must be open and not expired.
        - One evaluation per (rater, rated, project) — re-submitting updates.
        """
        project = self._project_repository.get_project(payload.project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        # Verify the course is open for evaluation.
        self._check_evaluation_window(project.course_id)

        # Verify rater is a member of the project.
        member_ids = self._project_repository.list_member_ids(payload.project_id)
        if rater_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project group.",
            )

        # Verify rated student is a member of the same project.
        if payload.rated_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The student you are evaluating is not in your project group.",
            )

        # Cannot evaluate yourself.
        if rater_id == payload.rated_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot evaluate yourself.",
            )

        # Check for existing evaluation (update instead of duplicate).
        existing = self._peer_evaluation_repository.get_evaluation_by_rater_and_rated(
            rater_id, payload.rated_id, payload.project_id
        )
        now = datetime.now(UTC)
        if existing is not None:
            existing.score = payload.score
            existing.remarks = payload.remarks
            existing.created_at = now
            saved = self._peer_evaluation_repository.save_evaluation(existing)
            is_update = True
        else:
            saved = PeerEvaluationRecord(
                evaluation_id=str(uuid4()),
                course_id=project.course_id,
                project_id=payload.project_id,
                rater_id=rater_id,
                rated_id=payload.rated_id,
                score=payload.score,
                remarks=payload.remarks,
                created_at=now,
            )
            self._peer_evaluation_repository.save_evaluation(saved)
            is_update = False

        append_action_audit(
            self._action_audits,
            actor_id=rater_id,
            actor_role=Role.STUDENT.value,
            action="submit_peer_evaluation",
            target_type="peer_evaluation",
            target_id=saved.evaluation_id,
            details={
                "course_id": project.course_id,
                "project_id": payload.project_id,
                "rated_id": payload.rated_id,
                "score": payload.score,
            },
        )

        return (
            PeerEvaluationResponse(
                evaluation_id=saved.evaluation_id,
                course_id=saved.course_id,
                project_id=saved.project_id,
                rater_id=saved.rater_id,
                rated_id=saved.rated_id,
                score=saved.score,
                remarks=saved.remarks,
                created_at=saved.created_at,
            ),
            is_update,
        )

    # ------------------------------------------------------------------
    # Student: update own evaluation (PATCH)
    # ------------------------------------------------------------------

    def update_evaluation(
        self,
        evaluation_id: str,
        payload: PeerEvaluationUpdate,
        rater_id: str,
    ) -> PeerEvaluationResponse:
        """Student updates their own evaluation (score and/or remarks).

        Only the rater can update their own evaluation.
        The evaluation window must still be open and not expired.
        """
        existing = self._peer_evaluation_repository.get_evaluation(evaluation_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found.",
            )

        # Only the rater can update.
        if existing.rater_id != rater_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own evaluations.",
            )

        # Verify the course is still open for evaluation.
        self._check_evaluation_window(existing.course_id)

        # Apply partial updates.
        if payload.score is not None:
            existing.score = payload.score
        if payload.remarks is not None:
            existing.remarks = payload.remarks

        existing.created_at = datetime.now(UTC)
        saved = self._peer_evaluation_repository.save_evaluation(existing)

        append_action_audit(
            self._action_audits,
            actor_id=rater_id,
            actor_role=Role.STUDENT.value,
            action="update_peer_evaluation",
            target_type="peer_evaluation",
            target_id=saved.evaluation_id,
            details={
                "course_id": existing.course_id,
                "project_id": existing.project_id,
                "rated_id": existing.rated_id,
                "score": saved.score,
            },
        )

        return PeerEvaluationResponse(
            evaluation_id=saved.evaluation_id,
            course_id=saved.course_id,
            project_id=saved.project_id,
            rater_id=saved.rater_id,
            rated_id=saved.rated_id,
            score=saved.score,
            remarks=saved.remarks,
            created_at=saved.created_at,
        )

    # ------------------------------------------------------------------
    # Student / Instructor: delete evaluation
    # ------------------------------------------------------------------

    def delete_evaluation(
        self,
        evaluation_id: str,
        rater_id: str,
        current_user_role: Role,
    ) -> None:
        """Delete an evaluation.

        - The rater can delete their own evaluation.
        - An instructor assigned to the course can delete any evaluation.
        """
        existing = self._peer_evaluation_repository.get_evaluation(evaluation_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found.",
            )

        is_rater = existing.rater_id == rater_id
        is_instructor_assigned = False

        if current_user_role in (Role.INSTRUCTOR, Role.ADMIN):
            is_instructor_assigned = self._project_repository.is_instructor_assigned(
                existing.course_id, rater_id
            )

        if not is_rater and not is_instructor_assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this evaluation.",
            )

        deleted = self._peer_evaluation_repository.delete_evaluation(evaluation_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found.",
            )

        append_action_audit(
            self._action_audits,
            actor_id=rater_id,
            actor_role=current_user_role.value,
            action="delete_peer_evaluation",
            target_type="peer_evaluation",
            target_id=evaluation_id,
            details={
                "course_id": existing.course_id,
                "project_id": existing.project_id,
                "rated_id": existing.rated_id,
            },
        )

    # ------------------------------------------------------------------
    # Student: view own evaluations (what they submitted about others)
    # ------------------------------------------------------------------

    def list_my_evaluations(
        self, rater_id: str, project_id: str | None = None
    ) -> list[PeerEvaluationResponse]:
        """Return evaluations submitted by the current student.

        Students can only see their own evaluations of others — never
        evaluations written about them or by other students.
        """
        records = self._peer_evaluation_repository.list_evaluations_by_rater(
            rater_id, project_id
        )
        return [
            PeerEvaluationResponse(
                evaluation_id=r.evaluation_id,
                course_id=r.course_id,
                project_id=r.project_id,
                rater_id=r.rater_id,
                rated_id=r.rated_id,
                score=r.score,
                remarks=r.remarks,
                created_at=r.created_at,
            )
            for r in records
        ]

    # ------------------------------------------------------------------
    # Instructor: view all evaluations
    # ------------------------------------------------------------------

    def get_project_evaluations(
        self, project_id: str, current_user_id: str
    ) -> PeerEvaluationSummary:
        """Instructor view: all evaluations for a project group."""
        project = self._project_repository.get_project(project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        # Verify instructor is assigned to the course.
        if not self._project_repository.is_instructor_assigned(
            project.course_id, current_user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to teach this course.",
            )

        records = self._peer_evaluation_repository.list_evaluations_by_project(
            project_id
        )

        evaluations = []
        total_score = 0
        for r in records:
            evaluations.append(self._to_instructor_view(r))
            total_score += r.score

        average_score = (
            round(total_score / len(evaluations), 2) if evaluations else None
        )

        return PeerEvaluationSummary(
            project_id=project_id,
            project_name=project.project_name,
            total_evaluations=len(evaluations),
            average_score=average_score,
            evaluations=evaluations,
        )

    def get_course_evaluations(
        self, course_id: str, current_user_id: str
    ):
        """Instructor view: all peer evaluations across all projects in a course."""
        from app.schemas.peer_evaluation import CoursePeerEvaluationSummary

        # Verify instructor is assigned to the course.
        if not self._project_repository.is_instructor_assigned(
            course_id, current_user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to teach this course.",
            )

        config = self._peer_evaluation_repository.get_config(course_id)
        projects = self._project_repository.list_projects(course_id)

        course_code = projects[0].course_code if projects else ""

        project_summaries = []
        total_evaluations = 0
        for project in projects:
            summary = self.get_project_evaluations(project.id, current_user_id)
            project_summaries.append(summary)
            total_evaluations += summary.total_evaluations

        return CoursePeerEvaluationSummary(
            course_id=course_id,
            course_code=course_code,
            is_open=config.is_open if config else False,
            expires_at=config.expires_at if config else None,
            total_projects=len(projects),
            total_evaluations=total_evaluations,
            projects=project_summaries,
        )

    def get_evaluation_status(
        self, course_id: str, student_id: str
    ):
        """Return whether a student can currently submit evaluations."""
        config = self._peer_evaluation_repository.get_config(course_id)
        if config is None or not config.is_open:
            return {
                "can_evaluate": False,
                "is_open": config.is_open if config else False,
                "opens_at": config.opens_at if config else None,
                "expires_at": config.expires_at if config else None,
                "message": "Peer evaluation is not currently open for this course.",
            }
        now = datetime.now(UTC)
        if config.opens_at is not None and now < config.opens_at:
            return {
                "can_evaluate": False,
                "is_open": True,
                "opens_at": config.opens_at,
                "expires_at": config.expires_at,
                "message": f"Peer evaluation has not opened yet. Opens at {config.opens_at.isoformat()}.",
            }
        if config.expires_at is not None and now > config.expires_at:
            return {
                "can_evaluate": False,
                "is_open": True,
                "opens_at": config.opens_at,
                "expires_at": config.expires_at,
                "message": "Peer evaluation has expired for this course.",
            }
        return {
            "can_evaluate": True,
            "is_open": True,
            "opens_at": config.opens_at,
            "expires_at": config.expires_at,
            "message": "Peer evaluation is open. You may evaluate your group members.",
        }

    def get_member_evaluations(
        self,
        project_id: str,
        member_id: str,
        current_user_id: str,
    ) -> MemberPeerEvaluationDetail:
        """Instructor view: scores, remarks, and outlier stats for one group member."""
        project = self._project_repository.get_project(project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        if not self._project_repository.is_instructor_assigned(
            project.course_id, current_user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to teach this course.",
            )

        member_ids = self._project_repository.list_member_ids(project_id)
        if member_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student is not a member of this project group.",
            )

        member = self._user_repository.get_by_id(member_id)
        received = [
            r
            for r in self._peer_evaluation_repository.list_evaluations_by_project(
                project_id
            )
            if r.rated_id == member_id
        ]

        received_scores = [float(r.score) for r in received]
        score_mean, score_stdev = _mean_and_sample_stdev(received_scores)

        evaluations: list[PeerEvaluationReceivedItem] = []
        for r in received:
            z = _z_score(float(r.score), score_mean, score_stdev)
            view = self._to_instructor_view(r)
            evaluations.append(
                PeerEvaluationReceivedItem(
                    **view.model_dump(),
                    is_score_outlier=_is_outlier(z),
                    score_z_score=_round_or_none(z),
                )
            )

        total_score = sum(r.score for r in received)
        average_score = _round_or_none(score_mean)

        enrolled_ids = self._project_repository.list_enrolled_student_ids(
            project.course_id
        )
        enrolled_set = set(enrolled_ids)
        course_records = self._peer_evaluation_repository.list_evaluations_by_course(
            project.course_id
        )
        totals_by_student: dict[str, int] = {sid: 0 for sid in enrolled_ids}
        students_with_evals: set[str] = set()
        for record in course_records:
            if record.rated_id not in enrolled_set:
                continue
            totals_by_student[record.rated_id] += record.score
            students_with_evals.add(record.rated_id)

        comparable_totals = [
            float(totals_by_student[sid]) for sid in students_with_evals
        ]
        course_mean, course_stdev = _mean_and_sample_stdev(comparable_totals)
        students_below_average = 0
        if course_mean is not None:
            students_below_average = sum(
                1
                for sid in enrolled_ids
                if totals_by_student[sid] < course_mean
            )

        total_z = None
        if received:
            total_z = _z_score(float(total_score), course_mean, course_stdev)
        is_total_outlier = _is_outlier(total_z)
        outlier_direction = None
        if is_total_outlier and total_z is not None:
            outlier_direction = "high" if total_z > 0 else "low"

        return MemberPeerEvaluationDetail(
            course_id=project.course_id,
            project_id=project_id,
            project_name=project.project_name,
            member_id=member_id,
            member_email=member.email if member else "",
            member_full_name=member.full_name if member else "",
            evaluations=evaluations,
            total_score=total_score,
            average_score=average_score,
            evaluation_count=len(evaluations),
            is_total_outlier=is_total_outlier,
            total_z_score=_round_or_none(total_z),
            outlier_direction=outlier_direction,
            course_average_total=_round_or_none(course_mean),
            course_total_score_std_dev=_round_or_none(course_stdev),
            enrolled_student_count=len(enrolled_ids),
            students_with_received_evaluations=len(students_with_evals),
            students_below_course_average=students_below_average,
        )

    def _to_instructor_view(
        self, record: PeerEvaluationRecord
    ) -> PeerEvaluationInstructorView:
        rater = self._user_repository.get_by_id(record.rater_id)
        rated = self._user_repository.get_by_id(record.rated_id)
        return PeerEvaluationInstructorView(
            evaluation_id=record.evaluation_id,
            course_id=record.course_id,
            project_id=record.project_id,
            rater_id=record.rater_id,
            rater_email=rater.email if rater else "",
            rater_full_name=rater.full_name if rater else "",
            rated_id=record.rated_id,
            rated_email=rated.email if rated else "",
            rated_full_name=rated.full_name if rated else "",
            score=record.score,
            remarks=record.remarks,
            created_at=record.created_at,
        )
