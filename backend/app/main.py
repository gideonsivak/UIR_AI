

"""Main FastAPI application for GIDEON PLANT."""



import hashlib

import json

import os

from pathlib import Path



from dotenv import load_dotenv

from fastapi import (

    FastAPI,

    HTTPException,

    UploadFile,

    File,

    Form,

)

from fastapi.middleware.cors import CORSMiddleware

from itsdangerous import (

    BadSignature,

    SignatureExpired,

    URLSafeTimedSerializer,

)

from pydantic import ValidationError



from .schemas import (

    AnalyzeRequest,

    AnalyzeResponse,

    DiagnosisCompleteRequest,

    DiagnosisCompleteResponse,

    DiagnosisStartRequest,

    DiagnosisStartResponse,

    InterviewAnswer,

)

from .ai_errors import AIServiceError

from .ai_service import (

    analyze_plant,

    start_diagnosis,

    complete_diagnosis,

)

from .routers import users, plants





load_dotenv(

    dotenv_path=Path(__file__).resolve().parents[1] / ".env"

)



app = FastAPI(title="GIDEON PLANT API")





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

# IMAGE SETTINGS

# --------------------------------------------------



ALLOWED_IMAGE_TYPES = {

    "image/jpeg",

    "image/png",

    "image/webp",

}



MAX_IMAGE_SIZE = 5 * 1024 * 1024





# --------------------------------------------------

# INTERVIEW TOKEN SETTINGS

# --------------------------------------------------



INTERVIEW_TOKEN_MAX_AGE = 30 * 60  # 30 minutes





def get_interview_serializer() -> URLSafeTimedSerializer:

    """

    Sign interview state with a server-side secret.



    Set DIAGNOSIS_SIGNING_KEY in backend/.env.

    Do not expose this key to the frontend.

    """



    secret = os.getenv("DIAGNOSIS_SIGNING_KEY", "")



    if len(secret) < 32:

        raise HTTPException(

            status_code=503,

            detail=(

                "Diagnostic interview signing key "

                "is not configured."

            ),

        )



    return URLSafeTimedSerializer(

        secret_key=secret,

        salt="gideon-plant-diagnostic-interview-v1",

    )





def image_fingerprint(image_bytes: bytes | None) -> str | None:

    """Bind an interview to the original image bytes."""



    if image_bytes is None:

        return None



    return hashlib.sha256(image_bytes).hexdigest()





def create_interview_token(

    request: DiagnosisStartRequest,

    questions: list,

    validation: dict,

    image_bytes: bytes | None,

) -> str:

    """Sign the original inputs, questions and validation."""



    payload = {

        "request": request.model_dump(mode="json"),

        "questions": [

            question.model_dump(mode="json")

            for question in questions

        ],

        "validation": validation,

        "image_sha256": image_fingerprint(image_bytes),

    }



    return get_interview_serializer().dumps(payload)





def read_interview_token(token: str) -> dict:

    """Verify the signed interview and its expiry."""



    try:

        payload = get_interview_serializer().loads(

            token,

            max_age=INTERVIEW_TOKEN_MAX_AGE,

        )



    except SignatureExpired as exc:

        raise HTTPException(

            status_code=422,

            detail=(

                "Your diagnostic interview has expired. "

                "Please start a new plant check."

            ),

        ) from exc



    except (BadSignature, ValueError, TypeError) as exc:

        raise HTTPException(

            status_code=422,

            detail=(

                "Invalid diagnostic interview. "

                "Please start a new plant check."

            ),

        ) from exc



    if not isinstance(payload, dict):

        raise HTTPException(

            status_code=422,

            detail="Invalid diagnostic interview data.",

        )



    return payload





# --------------------------------------------------

# SHARED IMAGE VALIDATION

# --------------------------------------------------



async def read_valid_image(

    image: UploadFile | None,

) -> tuple[bytes | None, str | None]:

    """Read and validate an optional uploaded image."""



    if image is None:

        return None, None



    mime_type = image.content_type



    if mime_type not in ALLOWED_IMAGE_TYPES:

        await image.close()

        raise HTTPException(

            status_code=400,

            detail="Only JPG, PNG, and WebP images are allowed.",

        )



    try:

        image_bytes = await image.read(MAX_IMAGE_SIZE + 1)

    finally:

        await image.close()



    if not image_bytes:

        raise HTTPException(

            status_code=400,

            detail="The uploaded image is empty.",

        )



    if len(image_bytes) > MAX_IMAGE_SIZE:

        raise HTTPException(

            status_code=413,

            detail="Image size must not exceed 5 MB.",

        )



    if mime_type == "image/jpeg":

        valid_signature = image_bytes.startswith(

            b"\xff\xd8\xff"

        )



    elif mime_type == "image/png":

        valid_signature = image_bytes.startswith(

            b"\x89PNG\r\n\x1a\n"

        )



    elif mime_type == "image/webp":

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



    return image_bytes, mime_type





def parse_plant_request(

    plant_name: str,

    plant_type: str,

    symptoms: str,

    location: str | None,

    schema_type,

):

    """Validate multipart form fields with Pydantic."""



    try:

        return schema_type(

            plant_name=plant_name,

            plant_type=plant_type,

            symptoms=symptoms,

            location=location,

        )



    except ValidationError as exc:

        raise HTTPException(

            status_code=422,

            detail="Please provide valid plant information.",

        ) from exc





def ai_http_error(exc: AIServiceError) -> HTTPException:

    return HTTPException(

        status_code=exc.status_code,

        detail=exc.public_message,

    )





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

    """Preserve the original text-only analysis API."""



    try:

        return analyze_plant(

            request.plant_name,

            request.plant_type,

            request.location,

            request.symptoms,

        )



    except AIServiceError as exc:

        raise ai_http_error(exc) from exc





# --------------------------------------------------

# EXISTING IMAGE + TEXT ANALYSIS

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

    """Preserve the original image analysis API."""



    request = parse_plant_request(

        plant_name,

        plant_type,

        symptoms,

        location,

        AnalyzeRequest,

    )



    image_bytes, image_mime_type = await read_valid_image(

        image

    )



    try:

        return analyze_plant(

            request.plant_name,

            request.plant_type,

            request.location,

            request.symptoms,

            image_bytes=image_bytes,

            image_mime_type=image_mime_type,

        )



    except AIServiceError as exc:

        raise ai_http_error(exc) from exc





# --------------------------------------------------

# NEW: START DIAGNOSTIC INTERVIEW

# --------------------------------------------------



@app.post(

    "/api/diagnosis/start",

    response_model=DiagnosisStartResponse,

    tags=["Smart Diagnosis"],

)

async def diagnosis_start(

    plant_name: str = Form(...),

    plant_type: str = Form(...),

    symptoms: str = Form(...),

    location: str | None = Form(None),

    image: UploadFile | None = File(None),

):

    """

    Validate the plant and generate 3–5 AI questions.



    Supports both text-only and image-based checks.

    """



    request = parse_plant_request(

        plant_name,

        plant_type,

        symptoms,

        location,

        DiagnosisStartRequest,

    )



    image_bytes, image_mime_type = await read_valid_image(

        image

    )



    try:

        result = start_diagnosis(

            request.plant_name,

            request.plant_type,

            request.location,

            request.symptoms,

            image_bytes=image_bytes,

            image_mime_type=image_mime_type,

        )



    except AIServiceError as exc:

        raise ai_http_error(exc) from exc



    try:

        response = DiagnosisStartResponse.model_validate(

            result

        )



    except ValidationError as exc:

        raise HTTPException(

            status_code=502,

            detail="Invalid diagnostic interview response.",

        ) from exc



    if response.validation.can_continue:

        response.interview_token = create_interview_token(

            request=request,

            questions=response.questions,

            validation=response.validation.model_dump(

                mode="json"

            ),

            image_bytes=image_bytes,

        )



    return response





# --------------------------------------------------

# NEW: COMPLETE DIAGNOSTIC INTERVIEW

# --------------------------------------------------



@app.post(

    "/api/diagnosis/complete",

    response_model=DiagnosisCompleteResponse,

    tags=["Smart Diagnosis"],

)

async def diagnosis_complete(

    plant_name: str = Form(...),

    plant_type: str = Form(...),

    symptoms: str = Form(...),

    interview_token: str = Form(...),

    answers_json: str = Form(...),

    location: str | None = Form(None),

    image: UploadFile | None = File(None),

):

    """

    Verify interview state, then produce final diagnosis.



    The original image must be resent at completion.

    """



    request = parse_plant_request(

        plant_name,

        plant_type,

        symptoms,

        location,

        DiagnosisStartRequest,

    )



    image_bytes, image_mime_type = await read_valid_image(

        image

    )



    payload = read_interview_token(interview_token)



    # Ensure the same plant details are submitted.

    if payload.get("request") != request.model_dump(

        mode="json"

    ):

        raise HTTPException(

            status_code=422,

            detail=(

                "Plant details changed during the interview. "

                "Please start a new plant check."

            ),

        )



    # Ensure the original image has not changed.

    if payload.get("image_sha256") != image_fingerprint(

        image_bytes

    ):

        raise HTTPException(

            status_code=422,

            detail=(

                "The plant image changed during the interview. "

                "Please start a new plant check."

            ),

        )



    # Validate the original signed questions.

    try:

        start_response = DiagnosisStartResponse(

            validation=payload["validation"],

            questions=payload["questions"],

        )



    except (KeyError, TypeError, ValidationError) as exc:

        raise HTTPException(

            status_code=422,

            detail="Invalid diagnostic interview data.",

        ) from exc



    if not start_response.validation.can_continue:

        raise HTTPException(

            status_code=422,

            detail=(

                "This plant check did not pass validation. "

                "Please start a new check."

            ),

        )



    # Parse submitted answers.

    try:

        raw_answers = json.loads(answers_json)



        if not isinstance(raw_answers, list):

            raise ValueError("Answers must be a list")



        answers = [

            InterviewAnswer.model_validate(item)

            for item in raw_answers

        ]



    except (

        json.JSONDecodeError,

        ValidationError,

        ValueError,

        TypeError,

    ) as exc:

        raise HTTPException(

            status_code=422,

            detail="Please provide valid interview answers.",

        ) from exc



    # Verify exactly one answer for every signed question.

    expected_questions = {

        question.id: question.question

        for question in start_response.questions

    }



    submitted_ids = [

        answer.question_id

        for answer in answers

    ]



    if (

        len(answers) != len(expected_questions)

        or len(set(submitted_ids)) != len(submitted_ids)

        or set(submitted_ids) != set(expected_questions)

    ):

        raise HTTPException(

            status_code=422,

            detail=(

                "Please answer every interview question "

                "exactly once."

            ),

        )



    for answer in answers:

        if (

            answer.question

            != expected_questions[answer.question_id]

        ):

            raise HTTPException(

                status_code=422,

                detail=(

                    "Interview questions have changed. "

                    "Please start a new plant check."

                ),

            )



    try:

        result = complete_diagnosis(

            plant_name=request.plant_name,

            plant_type=request.plant_type,

            location=request.location,

            symptom=request.symptoms,

            answers=answers,

            validation=start_response.validation,

            image_bytes=image_bytes,

            image_mime_type=image_mime_type,

        )



    except AIServiceError as exc:

        raise ai_http_error(exc) from exc



    return result





# --------------------------------------------------

# EXISTING DATABASE ROUTERS

# --------------------------------------------------



app.include_router(users.router)

app.include_router(plants.router)
