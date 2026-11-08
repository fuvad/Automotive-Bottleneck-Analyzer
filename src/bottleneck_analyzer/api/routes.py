"""HTTP transport around the unchanged Stage 6 workflow."""

import asyncio
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from bottleneck_analyzer.agents.contracts import InvestigationRequest
from bottleneck_analyzer.api.repository import APIRepository
from bottleneck_analyzer.api.runtime import AdmissionError, InvestigationRuntime
from bottleneck_analyzer.api.schemas import (
    AcceptedView,
    DatasetView,
    HistoryView,
    OptionsView,
    ProgressView,
    ResultView,
    SubmissionView,
    confirmed,
    project_result,
)
from bottleneck_analyzer.core.config import get_settings

router = APIRouter(prefix="/api")


def runtime(request: Request) -> InvestigationRuntime:
    return request.app.state.investigations


def repository(request: Request) -> APIRepository:
    return APIRepository(runtime(request).engine)


def api_error(status: int, code: str, **context) -> HTTPException:
    return HTTPException(
        status,
        detail={"code": code, "message": code.replace("_", " "), **context},
        headers={"Retry-After": "2"} if status in (429, 503) else None,
    )


@router.get("/datasets", response_model=list[DatasetView])
def datasets(
    request: Request, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)
):
    return repository(request).datasets(limit, offset)


@router.get("/datasets/{dataset_id}/options", response_model=OptionsView)
def options(dataset_id: UUID, request: Request):
    result = repository(request).options(dataset_id)
    if result is None:
        raise api_error(404, "dataset_not_found")
    settings = get_settings()
    return {
        **result,
        "shifts_truncated": len(result["shifts"]) == 1000,
        "methods": ["repair_duration", "failure_rate"],
        "simulation_max_days": settings.simulation_max_days,
        "simulation_max_replications": settings.simulation_max_replications,
    }


@router.post("/investigations", status_code=202, response_model=AcceptedView)
async def investigate(
    payload: InvestigationRequest,
    request: Request,
    submission_key: UUID = Header(alias="X-Submission-Key"),
):
    try:
        item = runtime(request).submit(submission_key, payload)
    except AdmissionError as exc:
        raise api_error(exc.status, exc.code) from None
    try:
        while True:
            view = item.view()
            if view["admission"] == "accepted" or item.accept():
                identifier = item.view()["investigation_id"]
                return {
                    "investigation_id": identifier,
                    "submission_key": submission_key,
                    "status_url": f"/api/investigations/{identifier}",
                    "result_url": f"/api/investigations/{identifier}/result",
                }
            if not view["worker_active"]:
                raise api_error(
                    item.error_status,
                    item.error or "admission_rejected",
                    submission_key=str(submission_key),
                )
            if monotonic() >= item.deadline or item.abandoned:
                item.abandon()
                raise api_error(
                    503,
                    "admission_timeout",
                    submission_key=str(submission_key),
                    reconcile_url=f"/api/submissions/{submission_key}",
                    execution_may_continue=item.accepted,
                )
            if await request.is_disconnected():
                item.abandon()
                raise api_error(503, "client_disconnected", submission_key=str(submission_key))
            await asyncio.sleep(0.01)
    finally:
        # ASGI cancellation/disconnect is not thread cancellation. Accepted work
        # continues; unaccepted work is prevented from crossing the audit gate.
        item.abandon()


@router.get("/submissions/{key}", response_model=SubmissionView)
def submission(key: UUID, request: Request):
    item = runtime(request).get(key)
    if item is None:
        raise api_error(404, "submission_not_found")
    with item.lock:
        candidate = item.candidate_id
        uncertain = item.error == "commit_unconfirmed" and item.committed_id is None
    if uncertain and candidate:
        row = repository(request).audit(candidate)
        if row:
            with item.lock:
                item.committed_id = candidate
    return item.view()


@router.get("/investigations", response_model=list[HistoryView])
def history(
    request: Request, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)
):
    return repository(request).history(limit, offset)


def get_row(request: Request, identifier: UUID, *, result=False):
    row = repository(request).audit(identifier, result=result)
    if row is None:
        raise api_error(404, "investigation_not_found")
    return row


def progress_view(request: Request, row: dict) -> ProgressView:
    final = confirmed(row)
    return ProgressView(
        investigation_id=row["id"],
        recorded_at=row["recorded_at"],
        persisted_status=row.get("status"),
        events=row.get("events") or [],
        final_confirmed=final,
        outcome=row.get("outcome") if final else None,
        execution="finalized" if final else runtime(request).execution(row["id"]),
    )


@router.get("/investigations/{identifier}", response_model=ProgressView)
def progress(identifier: UUID, request: Request):
    return progress_view(request, get_row(request, identifier))


@router.get("/investigations/{identifier}/result", response_model=ResultView)
def result(identifier: UUID, request: Request):
    row = get_row(request, identifier, result=True)
    if not confirmed(row):
        progress = progress_view(request, row)
        if progress.execution == "active":
            return JSONResponse(jsonable_encoder(progress), status_code=202)
        raise api_error(409, "execution_unconfirmed", investigation_id=str(identifier))
    try:
        return project_result(row)
    except (ValueError, TypeError, KeyError):
        raise api_error(503, "saved_result_unavailable") from None
