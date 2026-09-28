"""FastAPI backend wrapping the pure ingest/signals/scenarios/diagnosis
pipeline and the SQLite storage layer. This module only adapts existing
pure functions (src.cli.build_event, src.storage.repository) for HTTP --
no diagnosis/signal/scenario logic lives here.

Run with: uvicorn src.api.main:app --reload

The heavy SamplingContext (SECOM/vibration/WM-811K data + fitted sensor
model) is built once at startup, not per-request. Dependency functions
(get_ctx/get_rules/get_db_path) exist so tests can override them with
lightweight fakes via app.dependency_overrides instead of loading real data.
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.cli import DEFAULT_DB_PATH, build_event, load_rules
from src.ingest import validate as validate_mod
from src.scenarios.catalog import SamplingContext, build_sampling_context
from src.storage import repository as repo


class AppState:
    ctx: Optional[SamplingContext] = None
    rules: Optional[dict] = None
    db_path: str = DEFAULT_DB_PATH


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.rules = load_rules()
    state.ctx = build_sampling_context()
    yield


app = FastAPI(title="Handover PoC API", version="0.1.0", lifespan=lifespan)


def get_ctx() -> SamplingContext:
    if state.ctx is None:
        raise HTTPException(status_code=503, detail="sampling context not loaded yet")
    return state.ctx


def get_rules() -> dict:
    if state.rules is None:
        raise HTTPException(status_code=503, detail="rules not loaded yet")
    return state.rules


def get_db_path() -> str:
    return state.db_path


class GenerateRequest(BaseModel):
    scenario_id: str
    seed: int


class ValidateRequest(BaseModel):
    event: dict


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/scenarios")
def list_scenarios(ctx: SamplingContext = Depends(get_ctx)) -> dict:
    return ctx.scenarios


@app.post("/events/generate", status_code=201)
def generate_event(
    req: GenerateRequest,
    ctx: SamplingContext = Depends(get_ctx),
    rules: dict = Depends(get_rules),
    db_path: str = Depends(get_db_path),
) -> dict:
    if req.scenario_id not in ctx.scenarios:
        raise HTTPException(status_code=404, detail=f"Unknown scenario_id: {req.scenario_id}")
    try:
        event = build_event(req.scenario_id, req.seed, ctx, rules)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    repo.save_event(db_path, event)
    return event


@app.get("/events/{event_id}")
def get_event(event_id: str, db_path: str = Depends(get_db_path)) -> dict:
    event = repo.get_event(db_path, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@app.get("/events")
def list_events(
    scenario_id: Optional[str] = Query(default=None),
    primary_dept: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=200, gt=0),
    offset: int = Query(default=0, ge=0),
    db_path: str = Depends(get_db_path),
) -> list[dict]:
    return repo.list_events(db_path, scenario_id=scenario_id, primary_dept=primary_dept, limit=limit, offset=offset)


@app.post("/validate")
def validate_event(req: ValidateRequest, ctx: SamplingContext = Depends(get_ctx)) -> dict:
    event = req.event
    try:
        validate_mod.check_join_keys(
            event,
            secom_row_count=len(ctx.secom_df),
            vibration_file_count=len(ctx.vibration_load_result["files"]),
            wm811k_row_count=len(ctx.wm811k_df),
        )
        validate_mod.check_time_separation(event)
        validate_mod.check_unit_semantics(event)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok"}
