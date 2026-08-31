from pydantic import BaseModel, Field
from typing import Literal, Optional

class PeerEvaluation(BaseModel):
    evaluator: str = Field(description="Student giving feedback")
    evaluatee: str = Field(description="Student receiving feedback")
    rating: int = Field(description="Score from 1 to 5", ge=1, le=5)
    comments: str = Field(description="Qualitative feedback")

# # SECTION 4 — COLLABORATION & PEER EVALUATION
 
# class PeerEvaluationEntry(BaseModel):
#     """
#     A single anonymized peer evaluation record.
#     Evaluator identity is stripped by the Preprocessing Engine before inclusion.
#     """
 
#     evaluatee_student_id: str = Field(description="student_id of the person being evaluated.")
#     evaluatee_handle: str = Field(
#         description="Anonymized handle of the evaluatee for LLM rendering."
#     )
#     score_contribution: float = Field(
#         ge=1.0,
#         le=5.0,
#         description="Peer rating (1–5) for overall contribution to sprint deliverables.",
#     )
#     score_communication: float = Field(
#         ge=1.0,
#         le=5.0,
#         description="Peer rating (1–5) for quality and responsiveness of team communication.",
#     )
#     score_reliability: float = Field(
#         ge=1.0,
#         le=5.0,
#         description="Peer rating (1–5) for reliability: meeting commitments and deadlines.",
#     )
#     score_collaboration: float = Field(
#         ge=1.0,
#         le=5.0,
#         description=(
#             "Peer rating (1–5) for active collaboration: helping teammates, "
#             "reviewing code, unblocking others."
#         ),
#     )
#     qualitative_feedback: str = Field(
#         description=(
#             "Anonymized qualitative comment from this peer. "
#             "Direct quotes are included; evaluator names and identifying details "
#             "are stripped by the Preprocessing Engine before this bundle is assembled."
#         )
#     )
 
#     @property
#     def average_score(self) -> float:
#         return round(
#             (
#                 self.score_contribution
#                 + self.score_communication
#                 + self.score_reliability
#                 + self.score_collaboration
#             )
#             / 4,
#             2,
#         )
 
 
# class MeetingLog(BaseModel):
#     """Summary of a team meeting or standup within the sprint."""
 
#     meeting_date: date = Field(description="Date the meeting was held.")
#     meeting_type: Literal[
#         "standup", "sprint_planning", "retrospective", "ad_hoc", "client"
#     ] = Field(
#         description=(
#             "Meeting type. Presence of retrospectives signals healthy process discipline. "
#             "Absence of standups in a 2-week sprint is a collaboration concern."
#         )
#     )
#     duration_minutes: int = Field(ge=1, description="Meeting duration in minutes.")
#     attendee_student_ids: list[str] = Field(
#         description=(
#             "student_ids of attendees. Members absent from most meetings are "
#             "a Collaboration signal, especially for the absent member's contribution score."
#         )
#     )
#     summary: str = Field(
#         description=(
#             "Text summary from meeting minutes, transcript excerpt, or slide notes. "
#             "Used as direct evidence in LLM evaluation of Collaboration and Documentation."
#         )
#     )
#     action_items: list[str] = Field(
#         default_factory=list,
#         description=(
#             "Specific action items recorded. Presence of action items — and their "
#             "follow-through in subsequent meetings — signals team organisation."
#         ),
#     )
 
 
# class CollaborationSignals(BaseModel):
#     """Peer evaluations and team communication artifacts for the sprint."""
 
#     peer_evaluations: list[PeerEvaluationEntry] = Field(
#         default_factory=list,
#         description=(
#             "All peer evaluation submissions for this sprint, evaluator identity stripped. "
#             "Expect N-1 entries per student in a well-participating team."
#         ),
#     )
#     meeting_logs: list[MeetingLog] = Field(
#         default_factory=list,
#         description="Summaries of all team meetings held during the sprint.",
#     )
#     slide_deck_summary: Optional[str] = Field(
#         default=None,
#         description=(
#             "Extracted and summarised text from the sprint demo presentation slides. "
#             "None if no slides were submitted or extractable."
#         ),
#     )
#     communication_log_excerpt: Optional[str] = Field(
#         default=None,
#         max_length=3000,
#         description=(
#             "PII-stripped excerpt from team communication channel logs (Slack, Discord, etc.), "
#             "summarised by the Preprocessing Engine. Used as evidence for communication quality."
#         ),
#     )
 
#     def get_peer_scores_for_student(self, student_id: str) -> list[PeerEvaluationEntry]:
#         return [e for e in self.peer_evaluations if e.evaluatee_student_id == student_id]
 
#     def get_average_peer_score(self, student_id: str) -> Optional[float]:
#         entries = self.get_peer_scores_for_student(student_id)
#         if not entries:
#             return None
#         return round(sum(e.average_score for e in entries) / len(entries), 2)