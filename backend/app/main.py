from __future__ import annotations

import asyncio
import csv
import json
from json import JSONDecodeError
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .models import (
    ApplicationData,
    BatchJobStatus,
    BatchReviewItem,
    BatchReviewJobResponse,
    BatchReviewResponse,
    ReviewResponse,
    ReviewStatus,
)
from .services.image_processing import preprocess_image
from .services.ocr import OCRUnavailableError, extract_text
from .services.parsing import extract_label_fields
from .services.validation import validate_label

app = FastAPI(
    title="Alcohol Label Verification API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

batch_jobs: dict[str, BatchReviewJobResponse] = {}
batch_jobs_lock = Lock()


def parse_application_data(payload: str) -> ApplicationData:
    try:
        parsed = json.loads(payload)
    except JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Application data must be valid JSON.") from exc

    try:
        return ApplicationData.model_validate(parsed)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def run_review(image_bytes: bytes, application: ApplicationData) -> ReviewResponse:
    start = perf_counter()
    processed_image, preprocessing_notes = preprocess_image(image_bytes)
    ocr_result = extract_text(processed_image)
    extracted_fields = extract_label_fields(ocr_result.text)
    overall_status, field_results, warnings, summary = validate_label(
        application=application,
        raw_text=ocr_result.text,
        extracted_fields=extracted_fields,
        average_confidence=ocr_result.average_confidence,
    )
    timing_ms = round((perf_counter() - start) * 1000)

    return ReviewResponse(
        overall_status=overall_status,
        summary=summary,
        raw_text=ocr_result.text,
        extracted_fields=extracted_fields,
        field_results=field_results,
        preprocessing_notes=preprocessing_notes,
        warnings=warnings,
        average_confidence=ocr_result.average_confidence,
        timing_ms=timing_ms,
    )


def parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def application_from_csv_row(row: dict[str, str]) -> ApplicationData:
    return ApplicationData(
        brand_name=row.get("brand_name", "").strip(),
        class_type=row.get("class_type", "").strip() or None,
        alcohol_content=row.get("alcohol_content", "").strip() or None,
        net_contents=row.get("net_contents", "").strip() or None,
        bottler=row.get("bottler", "").strip() or None,
        country_of_origin=row.get("country_of_origin", "").strip() or None,
        imported=parse_bool(row.get("imported")),
    )


def normalize_csv_rows(decoded_csv: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(decoded_csv.splitlines()))
    return [
        {(key or "").strip().lower(): (value or "").strip() for key, value in raw_row.items()}
        for raw_row in rows
    ]


def summarize_batch_results(total_rows: int, results: list[BatchReviewItem]) -> BatchReviewResponse:
    passed = sum(item.overall_status == ReviewStatus.PASS for item in results)
    needs_review = sum(item.overall_status == ReviewStatus.NEEDS_REVIEW for item in results)
    failed = sum(item.overall_status == ReviewStatus.FAIL for item in results)

    return BatchReviewResponse(
        total_rows=total_rows,
        passed=passed,
        needs_review=needs_review,
        failed=failed,
        results=results,
    )


def update_batch_job(job_id: str, **changes: object) -> None:
    with batch_jobs_lock:
        current = batch_jobs.get(job_id)
        if current is None:
            return
        batch_jobs[job_id] = current.model_copy(update=changes)


def build_missing_image_item(row_number: int, application_id: str | None, image_filename: str) -> BatchReviewItem:
    return BatchReviewItem(
        row_number=row_number,
        application_id=application_id,
        image_filename=image_filename,
        overall_status=ReviewStatus.FAIL,
        summary="No uploaded image matched the CSV row.",
        error="Upload an image file whose name matches image_filename exactly.",
    )


def build_missing_filename_item(row_number: int, application_id: str | None) -> BatchReviewItem:
    return BatchReviewItem(
        row_number=row_number,
        application_id=application_id,
        overall_status=ReviewStatus.FAIL,
        summary="Missing image_filename in CSV row.",
        error="The CSV row did not include an image_filename value.",
    )


def process_batch_job(
    *,
    job_id: str,
    rows: list[dict[str, str]],
    image_lookup: dict[str, bytes],
) -> None:
    results: list[BatchReviewItem] = []
    update_batch_job(job_id, status=BatchJobStatus.RUNNING)

    try:
        for row_number, row in enumerate(rows, start=1):
            image_filename = row.get("image_filename") or ""
            application_id = row.get("application_id") or None

            if not image_filename:
                results.append(build_missing_filename_item(row_number, application_id))
            else:
                image_bytes = image_lookup.get(image_filename)
                if not image_bytes:
                    results.append(build_missing_image_item(row_number, application_id, image_filename))
                else:
                    try:
                        application = application_from_csv_row(row)
                        review = run_review(image_bytes=image_bytes, application=application)
                        results.append(
                            BatchReviewItem(
                                row_number=row_number,
                                application_id=application_id,
                                image_filename=image_filename,
                                overall_status=review.overall_status,
                                summary=review.summary,
                                field_results=review.field_results,
                            )
                        )
                    except ValidationError as exc:
                        results.append(
                            BatchReviewItem(
                                row_number=row_number,
                                application_id=application_id,
                                image_filename=image_filename,
                                overall_status=ReviewStatus.FAIL,
                                summary="The CSV row could not be validated.",
                                error=str(exc),
                            )
                        )

            summary = summarize_batch_results(len(rows), results)
            update_batch_job(
                job_id,
                processed_rows=row_number,
                passed=summary.passed,
                needs_review=summary.needs_review,
                failed=summary.failed,
                results=summary.results,
            )

        final_summary = summarize_batch_results(len(rows), results)
        update_batch_job(
            job_id,
            status=BatchJobStatus.COMPLETED,
            processed_rows=len(rows),
            passed=final_summary.passed,
            needs_review=final_summary.needs_review,
            failed=final_summary.failed,
            results=final_summary.results,
        )
    except Exception as exc:  # pragma: no cover - protective job-level failure path
        update_batch_job(
            job_id,
            status=BatchJobStatus.FAILED,
            error=str(exc),
        )


@app.exception_handler(OCRUnavailableError)
async def handle_ocr_unavailable(_: object, exc: OCRUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/review", response_model=ReviewResponse)
async def review_label(
    label_image: UploadFile = File(...),
    application_data: str = Form(...),
) -> ReviewResponse:
    image_bytes = await label_image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Label image upload was empty.")

    application = parse_application_data(application_data)
    return run_review(image_bytes=image_bytes, application=application)


@app.post("/api/batch-review", response_model=BatchReviewResponse)
async def batch_review(
    csv_file: UploadFile = File(...),
    images: list[UploadFile] = File(...),
) -> BatchReviewResponse:
    csv_bytes = await csv_file.read()
    if not csv_bytes:
        raise HTTPException(status_code=400, detail="Batch CSV upload was empty.")

    decoded_csv = csv_bytes.decode("utf-8-sig")
    rows = normalize_csv_rows(decoded_csv)
    image_lookup: dict[str, bytes] = {}

    for image in images:
        filename = image.filename or ""
        if not filename:
            continue
        image_lookup[filename] = await image.read()

    results: list[BatchReviewItem] = []

    for row_number, row in enumerate(rows, start=1):
        image_filename = row.get("image_filename") or None
        application_id = row.get("application_id") or None

        if not image_filename:
            results.append(build_missing_filename_item(row_number, application_id))
            continue

        image_bytes = image_lookup.get(image_filename)
        if not image_bytes:
            results.append(build_missing_image_item(row_number, application_id, image_filename))
            continue

        try:
            application = application_from_csv_row(row)
            review = run_review(image_bytes=image_bytes, application=application)
            results.append(
                BatchReviewItem(
                    row_number=row_number,
                    application_id=application_id,
                    image_filename=image_filename,
                    overall_status=review.overall_status,
                    summary=review.summary,
                    field_results=review.field_results,
                )
            )
        except ValidationError as exc:
            results.append(
                BatchReviewItem(
                    row_number=row_number,
                    application_id=application_id,
                    image_filename=image_filename,
                    overall_status=ReviewStatus.FAIL,
                    summary="The CSV row could not be validated.",
                    error=str(exc),
                )
            )

    return summarize_batch_results(len(rows), results)


@app.post("/api/batch-review-jobs", response_model=BatchReviewJobResponse, status_code=202)
async def create_batch_review_job(
    csv_file: UploadFile = File(...),
    images: list[UploadFile] = File(...),
) -> BatchReviewJobResponse:
    csv_bytes = await csv_file.read()
    if not csv_bytes:
        raise HTTPException(status_code=400, detail="Batch CSV upload was empty.")

    decoded_csv = csv_bytes.decode("utf-8-sig")
    rows = normalize_csv_rows(decoded_csv)
    image_lookup: dict[str, bytes] = {}

    for image in images:
        filename = image.filename or ""
        if not filename:
            continue
        image_lookup[filename] = await image.read()

    job_id = uuid4().hex
    job = BatchReviewJobResponse(
        job_id=job_id,
        status=BatchJobStatus.QUEUED,
        total_rows=len(rows),
        processed_rows=0,
        passed=0,
        needs_review=0,
        failed=0,
    )
    with batch_jobs_lock:
        batch_jobs[job_id] = job

    asyncio.create_task(
        asyncio.to_thread(
            process_batch_job,
            job_id=job_id,
            rows=rows,
            image_lookup=image_lookup,
        )
    )

    return job


@app.get("/api/batch-review-jobs/{job_id}", response_model=BatchReviewJobResponse)
async def get_batch_review_job(job_id: str) -> BatchReviewJobResponse:
    with batch_jobs_lock:
        job = batch_jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Batch review job not found.")

    return job


frontend_dist = Path("/app/frontend-dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
