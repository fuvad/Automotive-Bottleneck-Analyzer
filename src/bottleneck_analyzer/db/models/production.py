"""Typed PostgreSQL mappings for datasets and manufacturing history."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bottleneck_analyzer.db.base import Base


class Dataset(Base):
    __tablename__ = "dataset"
    __table_args__ = (CheckConstraint("end_time > start_time", name="ck_dataset_period"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    seed: Mapped[int]
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[str] = mapped_column(String(40))
    stations: Mapped[list["Station"]] = relationship(back_populates="dataset")


class DatasetRow:
    """All generated entities belong to one immutable dataset namespace."""

    id: Mapped[UUID] = mapped_column(primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("dataset.id"), index=True)


class Station(DatasetRow, Base):
    __tablename__ = "station"
    __table_args__ = (
        UniqueConstraint("dataset_id", "sequence", name="uq_station_sequence"),
        UniqueConstraint("dataset_id", "name", name="uq_station_name"),
        CheckConstraint("sequence BETWEEN 1 AND 7", name="ck_station_sequence"),
        CheckConstraint("planned_cycle_seconds > 0", name="ck_station_cycle"),
    )

    name: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int]
    planned_cycle_seconds: Mapped[float]
    dataset: Mapped[Dataset] = relationship(back_populates="stations")


class Buffer(DatasetRow, Base):
    __tablename__ = "buffer"
    __table_args__ = (
        UniqueConstraint("dataset_id", "upstream_station_id", name="uq_buffer_upstream"),
        CheckConstraint("capacity > 0", name="ck_buffer_capacity"),
        CheckConstraint("upstream_station_id <> downstream_station_id", name="ck_buffer_ends"),
    )

    upstream_station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    downstream_station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    capacity: Mapped[int]


class VehicleModel(DatasetRow, Base):
    __tablename__ = "vehicle_model"
    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_vehicle_model"),
        CheckConstraint("name IN ('SUV', 'Sedan')", name="ck_vehicle_model_name"),
    )

    name: Mapped[str] = mapped_column(String(10))


class Shift(DatasetRow, Base):
    """A dated production window; planned exclusions are stored separately."""

    __tablename__ = "shift"
    __table_args__ = (
        UniqueConstraint("dataset_id", "start_time", name="uq_shift_start"),
        CheckConstraint("end_time > start_time", name="ck_shift_period"),
        CheckConstraint("name IN ('shift_1', 'shift_2')", name="ck_shift_name"),
    )

    name: Mapped[str] = mapped_column(String(12))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone_name: Mapped[str] = mapped_column(String(40))


class CalendarExclusion(DatasetRow, Base):
    __tablename__ = "calendar_exclusion"
    __table_args__ = (CheckConstraint("end_time > start_time", name="ck_exclusion_period"),)

    shift_id: Mapped[UUID] = mapped_column(ForeignKey("shift.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(100))


class Vehicle(DatasetRow, Base):
    __tablename__ = "vehicle"
    __table_args__ = (
        UniqueConstraint("dataset_id", "release_sequence", name="uq_vehicle_release"),
        CheckConstraint("release_sequence > 0", name="ck_vehicle_release"),
    )

    model_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle_model.id"), index=True)
    release_sequence: Mapped[int]
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model: Mapped[VehicleModel] = relationship()


class SourceRecord(DatasetRow, Base):
    """Original fields and document text retained independently of normalization."""

    __tablename__ = "source_record"
    __table_args__ = (
        UniqueConstraint("dataset_id", "system", "source_id", name="uq_source_identity"),
        CheckConstraint(
            "system IN ('MES','SCADA','historian','CMMS','Andon','shift_notes','SOP')",
            name="ck_source_system",
        ),
        CheckConstraint("length(source_id) > 0", name="ck_source_id"),
        Index("ix_source_search", "search_vector", postgresql_using="gin"),
        Index("ix_source_station_time", "station_id", "recorded_at"),
    )

    system: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    station_id: Mapped[UUID | None] = mapped_column(ForeignKey("station.id"))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    text_content: Mapped[str] = mapped_column(Text)
    original_path: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english'::regconfig, text_content)", persisted=True),
    )
    embedding: Mapped[Any | None] = mapped_column(VECTOR())
    embedding_model: Mapped[str | None] = mapped_column(String(100))


class SourceRow(DatasetRow):
    source_record_id: Mapped[UUID] = mapped_column(ForeignKey("source_record.id"), unique=True)


class ProductionRecord(SourceRow, Base):
    __tablename__ = "production_record"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "station_id", name="uq_production_vehicle_station"),
        Index("ix_production_scope", "station_id", "shift_id", "completed_at"),
        CheckConstraint("completed_at > started_at", name="ck_production_period"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle.id"), index=True)
    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    shift_id: Mapped[UUID] = mapped_column(ForeignKey("shift.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    vehicle: Mapped[Vehicle] = relationship()


class StationEvent(SourceRow, Base):
    __tablename__ = "station_event"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_station_event_period"),
        CheckConstraint(
            "state IN ('running','blocked','starved','faulted','planned_downtime')",
            name="ck_station_event_state",
        ),
        Index("ix_station_event_period", "station_id", "start_time", "end_time"),
    )

    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    shift_id: Mapped[UUID] = mapped_column(ForeignKey("shift.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(24))
    duration_seconds: Mapped[float] = mapped_column(
        Float, Computed("EXTRACT(EPOCH FROM (end_time - start_time))", persisted=True)
    )


class FaultEvent(SourceRow, Base):
    __tablename__ = "fault_event"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_fault_period"),
        CheckConstraint(
            "category IN ('robot_fault','quality_stop','material_shortage',"
            "'mechanical_fault','electrical_fault','sensor_fault','other_equipment_fault')",
            name="ck_fault_category",
        ),
        Index("ix_fault_station_time", "station_id", "start_time"),
    )

    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    station_event_id: Mapped[UUID] = mapped_column(ForeignKey("station_event.id"), unique=True)
    category: Mapped[str] = mapped_column(String(30))
    equipment_id: Mapped[str] = mapped_column(String(40))
    fault_code: Mapped[str] = mapped_column(String(40))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float] = mapped_column(
        Float, Computed("EXTRACT(EPOCH FROM (end_time - start_time))", persisted=True)
    )
    station: Mapped[Station] = relationship()


class MaintenanceWorkOrder(SourceRow, Base):
    __tablename__ = "maintenance_work_order"
    __table_args__ = (
        CheckConstraint("closed_at IS NULL OR closed_at >= opened_at", name="ck_work_order_period"),
        CheckConstraint("status IN ('open','closed')", name="ck_work_order_status"),
    )

    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    fault_id: Mapped[UUID | None] = mapped_column(ForeignKey("fault_event.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12))
    recorded_cause: Mapped[str | None] = mapped_column(Text)
    fault: Mapped[FaultEvent | None] = relationship()


class AndonEvent(SourceRow, Base):
    __tablename__ = "andon_event"

    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    fault_id: Mapped[UUID | None] = mapped_column(ForeignKey("fault_event.id"), index=True)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    remarks: Mapped[str] = mapped_column(Text)


class ShiftHandoverNote(SourceRow, Base):
    __tablename__ = "shift_handover_note"

    shift_id: Mapped[UUID] = mapped_column(ForeignKey("shift.id"))
    station_id: Mapped[UUID | None] = mapped_column(ForeignKey("station.id"))
    fault_id: Mapped[UUID | None] = mapped_column(ForeignKey("fault_event.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text)


class HistorianObservation(SourceRow, Base):
    __tablename__ = "historian_observation"
    __table_args__ = (
        CheckConstraint("quality IN ('good','bad','missing')", name="ck_historian_quality"),
        CheckConstraint("quality <> 'good' OR value IS NOT NULL", name="ck_historian_good_value"),
        Index("ix_historian_station_time", "station_id", "observed_at"),
    )

    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    fault_id: Mapped[UUID | None] = mapped_column(ForeignKey("fault_event.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    measurement_name: Mapped[str] = mapped_column(String(80))
    value: Mapped[float | None]
    unit: Mapped[str] = mapped_column(String(20))
    quality: Mapped[str] = mapped_column(String(12))


class SOPDocument(SourceRow, Base):
    __tablename__ = "sop_document"
    __table_args__ = (UniqueConstraint("dataset_id", "title", "version", name="uq_sop_version"),)

    station_id: Mapped[UUID] = mapped_column(ForeignKey("station.id"))
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(20))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content: Mapped[str] = mapped_column(Text)
    sections: Mapped[list["SOPSection"]] = relationship(back_populates="document")


class SOPSection(SourceRow, Base):
    __tablename__ = "sop_section"
    __table_args__ = (UniqueConstraint("document_id", "sequence", name="uq_sop_section"),)

    document_id: Mapped[UUID] = mapped_column(ForeignKey("sop_document.id"))
    sequence: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    document: Mapped[SOPDocument] = relationship(back_populates="sections")


class EvidenceLink(DatasetRow, Base):
    __tablename__ = "evidence_link"
    __table_args__ = (
        UniqueConstraint("from_record_id", "to_record_id", name="uq_evidence_pair"),
        CheckConstraint("from_record_id <> to_record_id", name="ck_evidence_distinct"),
        CheckConstraint("relationship IN ('direct','inferred')", name="ck_evidence_relationship"),
        CheckConstraint("length(basis) > 0", name="ck_evidence_basis"),
    )

    from_record_id: Mapped[UUID] = mapped_column(ForeignKey("source_record.id"), index=True)
    to_record_id: Mapped[UUID] = mapped_column(ForeignKey("source_record.id"), index=True)
    relationship: Mapped[str] = mapped_column(String(12))
    basis: Mapped[str] = mapped_column(Text)


class ModelConfiguration(DatasetRow, Base):
    """Storage for later approved simulation configurations; no execution here."""

    __tablename__ = "model_configuration"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_model_version"),)

    version: Mapped[str] = mapped_column(String(80))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SimulationRun(DatasetRow, Base):
    __tablename__ = "simulation_run"

    configuration_id: Mapped[UUID] = mapped_column(ForeignKey("model_configuration.id"))
    seed: Mapped[int]
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationAudit(DatasetRow, Base):
    __tablename__ = "investigation_audit"

    question: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(String(40))
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    final_answer: Mapped[str | None] = mapped_column(Text)
