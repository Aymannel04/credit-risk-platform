"""The scoring API: a thin, strict web layer on top of the JSON model file.

It reads models/scorecard_v2.json at start-up (and refuses to start if the file is missing or damaged), scores loans,
and explains them. It does NOT train, store or log loan data, and it does NOT decide to approve or refuse.

Run locally (from the repo root):
    .venv/Scripts/python -m uvicorn service.main:create_app --factory --reload
then open http://127.0.0.1:8000/docs to try it with buttons.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from credit.serving.model_file import explain_loan, load_model, score_loan
from service.schemas import (
    ExplainResponse,
    HealthResponse,
    LoanRequest,
    ModelInfoResponse,
    Reason,
    ScoreResponse,
)

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "scorecard_v2.json"
CAUTION = ("Through-the-cycle probability: in calm years it has been 1.4 to 2.6 times the real default rate. "
           "This is a portfolio project, not a lending decision.")


def to_model_input(req: LoanRequest) -> dict:
    """Translate the API fields into the model's features (the spread and the borrower flag are derived here)."""
    spread = None if req.interest_rate is None or req.reference_rate is None else req.interest_rate - req.reference_rate
    several = None if req.number_of_borrowers is None else (1.0 if req.number_of_borrowers >= 2 else 0.0)
    return {
        "credit_score": None if req.credit_score is None else float(req.credit_score),
        "dti": req.dti, "rate_spread": spread, "ltv": req.ltv, "cltv": req.cltv, "several_borrowers": several,
        "mi_pct": req.mi_pct, "orig_term": None if req.term_months is None else float(req.term_months), "purpose": req.purpose,
    }


def outside_range(model: dict, features: dict) -> list[str]:
    ranges = model.get("training_ranges", {})
    out = []
    for name, value in features.items():
        r = ranges.get(name)
        if r is not None and isinstance(value, (int, float)) and not (r[0] <= value <= r[1]):
            out.append(name)
    return out


def create_app(model_path: str | Path | None = None) -> FastAPI:
    path = Path(model_path or os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model = load_model(path)  # raises if the file is missing, malformed or tampered with: the service never starts half-ready
        yield

    app = FastAPI(
        title="Credit scoring API (portfolio project)",
        version="1.0.0",
        description="Scores a mortgage application with the v2 WoE scorecard and explains the score with fixed reason sentences. "
                    "Not a lending product. See /model-info for the known limits.",
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def reject_invalid(_: Request, exc: RequestValidationError):
        # Report where and why, but never echo the bad value back: an `Infinity` input would make the error response itself fail to encode.
        errors = [{"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    def model_of(request: Request) -> dict:
        return request.app.state.model

    def scored(request: Request, req: LoanRequest):
        model = model_of(request)
        features = to_model_input(req)
        try:
            return model, features, score_loan(model, features)
        except ValueError as e:  # should be unreachable after validation: report instead of crashing
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/health", response_model=HealthResponse, summary="Is the service alive, and which model does it run?")
    def health(request: Request):
        m = model_of(request)
        return HealthResponse(status="ok", model_id=m["model_id"], model_version=m["version"])

    @app.get("/model-info", response_model=ModelInfoResponse, summary="Identity, scale, inputs and known limits of the model")
    def model_info(request: Request):
        m = model_of(request)
        return ModelInfoResponse(
            model=m["model"], model_id=m["model_id"], model_version=m["version"], trained_on=m.get("trained_on", ""),
            adopted_by=m.get("adopted_by", ""), scaling=m["scaling"],
            features={n: m["features"][n]["labels"] for n in m["feature_order"]},
            training_ranges=m.get("training_ranges", {}), known_limits=m["known_limits"])

    @app.post("/score", response_model=ScoreResponse, summary="Score one loan: points and probability of default")
    def score(request: Request, req: LoanRequest):
        model, features, out = scored(request, req)
        return ScoreResponse(model_id=model["model_id"], model_version=model["version"], score=out["score"],
                             probability_of_default=out["probability_of_default"],
                             outside_training_range=outside_range(model, features), caution=CAUTION)

    @app.post("/explain", response_model=ExplainResponse, summary="Score one loan and give the reasons (fixed sentences)")
    def explain(request: Request, req: LoanRequest, top_k: int = Query(4, ge=1, le=9)):
        model, features, out = scored(request, req)
        return ExplainResponse(
            model_id=model["model_id"], model_version=model["version"], score=out["score"],
            probability_of_default=out["probability_of_default"], outside_training_range=outside_range(model, features),
            caution=CAUTION, reasons=[Reason(**r) for r in explain_loan(model, out, top_k=top_k)],
            points=out["points"], bands=out["bands"])

    return app
