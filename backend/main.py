"""backend/main.py
FastAPI entry‑point for ClauseGuard.
Only stub implementations are provided now – the real model logic will be wired later.
"""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
import logging
import sys
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import schemas, model_loader
from .services import (
    ConsumerExplanationEngine,
    EvidenceFusionEngine,
    PriceAnalyzer,
    TextPredictor,
    ModelUnavailableError,
    PredictionExecutionError,
    ConsumerRiskGate,
    MiniLMExplanationLayer,
    AskClauseGuardService,
)
from .vision import VisionService

app = FastAPI(title="ClauseGuard API")
text_predictor = TextPredictor()
price_analyzer = PriceAnalyzer()
evidence_fusion_engine = EvidenceFusionEngine(
    text_predictor=text_predictor,
    price_analyzer=price_analyzer,
)
consumer_explanation_engine = ConsumerExplanationEngine(
    fusion_engine=evidence_fusion_engine,
)
consumer_risk_gate = ConsumerRiskGate()
minilm_explanation_layer = MiniLMExplanationLayer()
ask_clauseguard_service = AskClauseGuardService()
_ask_requests: dict[str, deque[float]] = defaultdict(deque)
_ask_rate_limit = int(os.getenv("CLAUSEGUARD_ASK_RATE_LIMIT", "30"))
_ask_rate_window = 60.0
vision_service = None
MAX_VISION_BYTES = 5 * 1024 * 1024
SUPPORTED_VISION_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp"}



# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
_logger = logging.getLogger("clauseguard_backend")


def _ask_error_response(request: Request, code: str, message: str, status_code: int, request_id: str | None = None) -> JSONResponse:
    request_id = request_id or request.headers.get("X-Request-ID") or uuid.uuid4().hex
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    if request.url.path == "/ask":
        return _ask_error_response(
            request,
            "ASK_CONTEXT_INVALID",
            "The current ClauseGuard analysis context could not be validated. Please refresh the analysis and try again.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            request_id=request_id,
        )
    sanitized = []
    for err in exc.errors():
        item = {
            "loc": [str(part) for part in err.get("loc", [])],
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        }
        if "ctx" in err and isinstance(err["ctx"], dict):
            safe_ctx = {}
            for key, value in err["ctx"].items():
                safe_ctx[str(key)] = str(value)
            item["ctx"] = safe_ctx
        sanitized.append(item)
    return JSONResponse(
        status_code=422,
        content={"detail": sanitized},
        headers={"X-Request-ID": request_id},
    )


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _logger.exception("Request failed request_id=%s path=%s", request_id, request.url.path)
        raise
    response.headers["X-Request-ID"] = response.headers.get("X-Request-ID", getattr(request.state, "request_id", request_id))
    _logger.info(
        "Request complete request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response

@app.on_event("startup")
async def startup_event():
    _logger.info("Initializing ClauseGuard API...")
    try:
        model_loader.load_model()
        _logger.info("Model loaded successfully.")
    except Exception as exc:
        _logger.error("Failed to load model on startup: %s", str(exc))

# CORS – strictly scoped to configured frontend origins and Chrome extensions
_configured_origins = [
    origin.strip()
    for origin in os.getenv(
        "CLAUSEGUARD_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_origins,
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)

@app.get("/")
async def root():
    """Root status endpoint."""
    return {"message": "ClauseGuard API", "status": "running"}

@app.get("/health", response_model=schemas.HealthResponse)
async def health():
    """Return basic health information.
    model_loaded reflects whether the singleton model could be loaded at startup.
    """
    return schemas.HealthResponse(
        status="healthy",
        model_loaded=model_loader.is_model_loaded(),
        model_version=model_loader.get_model_version(),
    )


@app.get("/ready")
async def ready():
    """Readiness probe for deployments that require the text model."""
    if not model_loader.is_model_loaded():
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={
            "status": "not_ready",
            "model_loaded": False,
            "model_version": model_loader.get_model_version(),
        })
    return {"status": "ready", "model_loaded": True, "model_version": model_loader.get_model_version()}

@app.post("/predict", response_model=schemas.PredictResponse)
async def predict(request: schemas.PredictRequest):
    """Run a prediction on the supplied text.
    Input validation is performed by the Pydantic model.
    Delegates to the TextPredictor service layer.
    """
    try:
        return text_predictor.predict(request.text)
    except ModelUnavailableError as exc:
        _logger.exception("Model unavailable on /predict: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model service unavailable",
        )
    except PredictionExecutionError as exc:
        _logger.exception("Prediction failure on /predict: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction execution failed",
        )
    except Exception as exc:
        _logger.exception("Unexpected error in /predict: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction execution failed",
        )

@app.post("/analyze-price", response_model=schemas.PriceAnalysisResponse)
async def analyze_price(request: schemas.PriceAnalysisRequest):
    """Analyze text for explicit monetary entities.
    Input validation is performed by the Pydantic model.
    Delegates to the PriceAnalyzer service layer.
    """
    try:
        return price_analyzer.analyze(request.text)
    except Exception as exc:
        _logger.exception("Unexpected error in /analyze-price: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Price analysis execution failed",
        )


@app.post("/vision/predict")
async def vision_predict(request: Request, frame_id: str | None = None):
    """Run the trained Vision detector and return image evidence."""
    global vision_service
    content_type = request.headers.get("content-type", "image/png").split(";", 1)[0].lower()
    if content_type not in SUPPORTED_VISION_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image content type")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_VISION_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image payload is too large")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content length")
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image body is required")
    if len(image_bytes) > MAX_VISION_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image payload is too large")

    try:
        if vision_service is None:
            vision_service = VisionService()
        suffix = {
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
        }.get(content_type, ".png")
        return vision_service.predict_bytes(image_bytes, suffix=suffix, frame_id=frame_id)
    except Exception as exc:
        _logger.exception("Vision inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vision model unavailable or image inference failed",
        )

@app.post("/fuse-evidence", response_model=schemas.EvidenceFusionResponse)
async def fuse_evidence(request: schemas.EvidenceFusionRequest):
    """Fuse multi-source evidence across text, price, UI, and behavioral signals.
    Input validation is performed by the Pydantic model.
    Delegates to the EvidenceFusionEngine service layer.
    """
    try:
        return evidence_fusion_engine.fuse(request)
    except Exception as exc:
        _logger.exception("Unexpected error in /fuse-evidence: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evidence fusion execution failed",
        )


@app.post("/explain", response_model=schemas.ExplanationResponse)
async def explain(request: schemas.ExplanationRequest):
    """Generate evidence-grounded consumer explanation and practical recommendations.
    Input validation is performed by the Pydantic model.
    Delegates to the ConsumerExplanationEngine service layer.
    """
    try:
        return consumer_explanation_engine.explain(request)
    except Exception as exc:
        _logger.exception("Unexpected error in /explain: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Consumer explanation execution failed",
        )


@app.post("/analyze", response_model=schemas.AnalyzeResponse)
async def analyze(request: schemas.AnalyzeRequest):
    """Unified analysis endpoint that fuses text, pricing, and UI evidence into one canonical risk outcome."""
    try:
        fusion_request = schemas.EvidenceFusionRequest(
            text=request.text,
            price_analysis=request.price_analysis,
            dom_evidence=request.dom_evidence,
            behavior_evidence=request.behavior_evidence,
            raw_evidence=request.raw_evidence,
            image_evidence=request.image_evidence,
            jurisdiction=request.jurisdiction,
            transaction_date=request.transaction_date,
            entity_type=request.entity_type,
            member_state=request.member_state,
        )
        fusion_response = evidence_fusion_engine.fuse(fusion_request)
        gate = consumer_risk_gate.evaluate(fusion_response)
        evidence_context = schemas.ExplanationContext(
            risk_result={
                "risk_score": fusion_response.risk_score,
                "risk_level": fusion_response.risk_level,
                "risk_detected": fusion_response.risk_detected,
                "gate_decision": gate["decision"],
            },
            pattern=fusion_response.primary_pattern or fusion_response.potential_pattern,
            evidence_ids=[item.evidence_id for item in fusion_response.evidence],
            evidence_descriptions=[item.description for item in fusion_response.evidence],
            consequence=(fusion_response.consumer_consequence.description if fusion_response.consumer_consequence else None),
            financial_exposure=(fusion_response.financial_impact.known_total if fusion_response.financial_impact else None),
            consumer_effort=(
                fusion_response.intelligence_analysis.consumer_consequences[0].consumer_effort
                if fusion_response.intelligence_analysis and fusion_response.intelligence_analysis.consumer_consequences
                else None
            ),
            decision_context=(
                fusion_response.transaction_state.get("decision_context")
                if fusion_response.transaction_state else None
            ),
            regulatory_assessment=(
                fusion_response.intelligence_analysis.model_dump()
                if fusion_response.intelligence_analysis else None
            ),
            requires_context=fusion_response.requires_context,
            provenance=[
                item.provenance.model_dump() if hasattr(item.provenance, "model_dump")
                else {"source": item.source, "provenance": item.provenance}
                for item in fusion_response.evidence
            ],
        )
        explanation_response = consumer_explanation_engine.explain(
            schemas.ExplanationRequest(
                fusion_response=fusion_response,
                explanation_context=evidence_context,
            )
        )
        explanation_response = minilm_explanation_layer.enhance(explanation_response, evidence_context)
        return schemas.AnalyzeResponse(
            status="ok",
            risk_score=float(fusion_response.risk_score),
            score_breakdown=fusion_response.score_breakdown,
            risk_level=fusion_response.risk_level,
            risk_detected=bool(fusion_response.risk_detected or fusion_response.dark_pattern),
            potential_pattern=fusion_response.potential_pattern,
            dark_pattern=fusion_response.dark_pattern,
            confidence=fusion_response.confidence,
            model_version=model_loader.get_model_version(),
            evidence_count=len(fusion_response.evidence or []),
            consumer_gate=gate,
            explanation=explanation_response,
            explanation_context=evidence_context,
            evidence=fusion_response.evidence,
            context_requirements=fusion_response.context_requirements,
            regulatory_assessment=fusion_response.intelligence_analysis,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        _logger.exception("Unexpected error in /analyze: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unified analysis execution failed",
        )


@app.post("/ask", response_model=schemas.AskResponse)
async def ask_clauseguard(request: schemas.AskRequest, http_request: Request):
    """Explain an allowlisted snapshot of an existing canonical assessment."""
    now = time.time()
    client_key = http_request.client.host if http_request.client else "unknown"
    recent = _ask_requests[client_key]
    while recent and now - recent[0] > _ask_rate_window:
        recent.popleft()
    if len(recent) >= _ask_rate_limit:
        return _ask_error_response(
            http_request,
            "ASK_RATE_LIMITED",
            "Ask ClauseGuard is temporarily rate limited. Please try again shortly.",
            status.HTTP_429_TOO_MANY_REQUESTS,
            request.request_id,
        )
    recent.append(now)

    if request.context_generated_at:
        age = (datetime.now(timezone.utc) - request.context_generated_at.astimezone(timezone.utc)).total_seconds()
        if age > 30 * 60:
            return _ask_error_response(
                http_request,
                "ASK_CONTEXT_STALE",
                "The page analysis has changed. Refresh the current ClauseGuard analysis before asking this question.",
                status.HTTP_409_CONFLICT,
                request.request_id,
            )

    request_id = request.request_id or http_request.headers.get("X-Request-ID") or uuid.uuid4().hex
    http_request.state.request_id = request_id
    try:
        response = ask_clauseguard_service.answer(
            request_id,
            request.question,
            request.context,
            conversation_history=request.conversation_history,
            prefer_local_llm=request.prefer_local_llm,
        )
    except RuntimeError:
        _logger.exception("Ask provider unavailable request_id=%s", request_id)
        return _ask_error_response(
            http_request,
            "ASK_PROVIDER_UNAVAILABLE",
            "Ask ClauseGuard's answer service is temporarily unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception:
        _logger.exception("Ask execution failed request_id=%s", request_id)
        return _ask_error_response(
            http_request,
            "ASK_SERVER_ERROR",
            "Ask ClauseGuard could not complete the request. Please try again.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    _logger.info(
        "Ask trace request_id=%s question=%r intent=%s response_mode=%s evidence_ids=%s pattern=%s consequence=%s recommendation=%s llm_called=%s fallback=%s",
        request_id,
        request.question,
        response.intent,
        response.response_mode,
        response.evidence_ids,
        request.context.active_finding.pattern if request.context.active_finding else request.context.primary_pattern,
        response.intent in {"WHY_WARNING", "EXPLAIN_PATTERN", "CONSEQUENCE", "ASSESSMENT_SEPARATION"},
        response.intent in {"WHAT_SHOULD_I_DO", "ASSESSMENT_SEPARATION"},
        response.response_mode == "GROUNDED_LLM",
        response.fallback_used,
    )
    return response



@app.get("/model-info", response_model=schemas.ModelInfoResponse)
async def model_info():
    """Expose static metadata about the model version.
    In a real system this could be loaded from a JSON file.
    """
    metadata = model_loader.get_model_metadata()
    return schemas.ModelInfoResponse(
        model_version=model_loader.get_model_version(),
        algorithm=metadata.get("algorithm", "TF-IDF + CalibratedClassifierCV"),
        dataset_version=metadata.get("dataset_version", "ClauseGuard-Text-V3"),
        training_date=metadata.get("training_date", "unknown"),
        python_version=metadata.get("python_version", "unknown"),
        scikit_learn_version=metadata.get("sklearn_version", metadata.get("scikit_learn_version", "unknown")),
        expected_input="plain text",
        output_labels=["not_dark_pattern", "potential_dark_pattern"],
        artifact=metadata.get("artifact"),
        artifact_sha256=model_loader.get_model_sha256(),
    )
