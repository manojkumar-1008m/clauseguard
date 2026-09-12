"""backend/main.py
FastAPI entry‑point for ClauseGuard.
Only stub implementations are provided now – the real model logic will be wired later.
"""

from fastapi import FastAPI, HTTPException, Request, status
import logging
import sys
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
vision_service = None



# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
_logger = logging.getLogger("clauseguard_backend")

@app.on_event("startup")
async def startup_event():
    _logger.info("Initializing ClauseGuard API...")
    try:
        model_loader.load_model()
        _logger.info("Model loaded successfully.")
    except Exception as exc:
        _logger.error("Failed to load model on startup: %s", str(exc))

# CORS – strictly scoped to local dev frontend and Chrome extension origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
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
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image body is required")

    try:
        if vision_service is None:
            vision_service = VisionService()
        content_type = request.headers.get("content-type", "image/png").split(";", 1)[0].lower()
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



@app.get("/model-info", response_model=schemas.ModelInfoResponse)
async def model_info():
    """Expose static metadata about the model version.
    In a real system this could be loaded from a JSON file.
    """
    return schemas.ModelInfoResponse(
        model_version=model_loader.get_model_version(),
        algorithm="TF-IDF(1,3, sublinear) + CalibratedClassifierCV(LinearSVC)",
        dataset_version="ClauseGuard-Text-V3",
        training_date="2026-09-08",
        python_version="3.13",
        scikit_learn_version="1.7.1",
        expected_input="plain text",
        output_labels=["not_dark_pattern", "potential_dark_pattern"],
    )
