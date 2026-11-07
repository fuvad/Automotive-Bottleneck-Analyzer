"""Foundational enums shared by future workflows and domain models."""

from enum import StrEnum


class QuestionIntent(StrEnum):
    """Supported investigation question groups."""

    CONSTRAINT_OUTPUT_LOSS = "constraint_output_loss"
    SEGMENTATION = "segmentation"
    CAUSES = "causes"
    WHAT_IF = "what_if"
    COMBINED = "combined"


class InvestigationStatus(StrEnum):
    """Lifecycle states for a persisted investigation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class InterventionMethod(StrEnum):
    """Supported robot-fault intervention semantics."""

    REPAIR_DURATION = "repair_duration"
    FAILURE_RATE = "failure_rate"


class EvidenceRelationship(StrEnum):
    """How an evidence record is connected to an investigation."""

    DIRECT = "direct"
    INFERRED = "inferred"
