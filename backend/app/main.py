
"""Main FastAPI application for GIDEON PLANT."""

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
)

from fastapi.middleware.cors import CORSMiddleware

from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
)

from .ai_errors import AIServiceError
from .ai_service import analyze_plant
from .routers import users, plants


app = FastAPI(
    title="GIDEON PLANT API"
)


# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# IMAGE VALIDATION SETTINGS
# --------------------------------------------------

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get(
    "/api/health",
    tags=["Plant Analysis"],
)
def health():
    return {
        "status": "ok",
        "service": "GIDEON PLANT API",
    }


# --------------------------------------------------
# EXISTING TEXT-ONLY ANALYSIS
# --------------------------------------------------

@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    tags=["Plant Analysis"],
)
def analyze(request: AnalyzeRequest):
    """Analyze plant information without an image."""

    try:
        return analyze_plant(
            request.plant_name,
            request.plant_type,
            request.location,
            request.symptoms,
        )

    except AIServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.public_message,
        ) from exc


# --------------------------------------------------
# NEW IMAGE + TEXT ANALYSIS
# --------------------------------------------------

@app.post(
    "/api/analyze-image",
    response_model=AnalyzeResponse,
    tags=["Plant Analysis"],
)
async def analyze_image(
    plant_name: str = Form(...),
    plant_type: str = Form(...),
    symptoms: str = Form(...),
    location: str | None = Form(None),
    image: UploadFile = File(...),
):
    """Analyze plant details together with an uploaded image."""

    # Validate text using the existing Pydantic schema.
    try:
        request = AnalyzeRequest(
            plant_name=plant_name,
            plant_type=plant_type,
            location=location,
            symptoms=symptoms,
        )

    except Exception as exc:
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            raise HTTPException(
                status_code=422,
                detail="Please provide valid plant information.",
            ) from exc

        raise

    # Validate the declared image MIME type.
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only JPG, PNG, and WebP images are allowed."
            ),
        )

    try:
        # Read at most MAX_IMAGE_SIZE + 1 bytes.
        # This avoids loading an unlimited file into memory.
        image_bytes = await image.read(
            MAX_IMAGE_SIZE + 1
        )

    finally:
        await image.close()

    # Reject empty images.
    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded image is empty.",
        )

    # Reject images larger than 5 MB.
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image size must not exceed 5 MB.",
        )

    # Validate the actual file signature.
    if image.content_type == "image/jpeg":
        valid_signature = image_bytes.startswith(
            b"\xff\xd8\xff"
        )

    elif image.content_type == "image/png":
        valid_signature = image_bytes.startswith(
            b"\x89PNG\r\n\x1a\n"
        )

    elif image.content_type == "image/webp":
        valid_signature = (
            len(image_bytes) >= 12
            and image_bytes[:4] == b"RIFF"
            and image_bytes[8:12] == b"WEBP"
        )

    else:
        valid_signature = False

    if not valid_signature:
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file does not match "
                "its declared image format."
            ),
        )

    # Send image and text to Gemini.
    try:
        result = analyze_plant(
            request.plant_name,
            request.plant_type,
            request.location,
            request.symptoms,
            image_bytes=image_bytes,
            image_mime_type=image.content_type,
        )

        # Validate the final response through FastAPI's
        # existing AnalyzeResponse response_model.
        return result

    except AIServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.public_message,
        ) from exc


# --------------------------------------------------
# EXISTING DATABASE ROUTERS
# --------------------------------------------------

app.include_router(users.router)
app.include_router(plants.router)
