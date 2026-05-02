from app import main
from app.models import (
    BatchJobStatus,
    BatchReviewJobResponse,
    FieldReviewResult,
    LabelFields,
    ReviewResponse,
    ReviewStatus,
)


def make_review(status: ReviewStatus, summary: str) -> ReviewResponse:
    return ReviewResponse(
        overall_status=status,
        summary=summary,
        raw_text="",
        extracted_fields=LabelFields(),
        field_results=[
            FieldReviewResult(
                field="brand_name",
                label="Brand name",
                status=status,
                reason=summary,
            )
        ],
        preprocessing_notes=[],
        warnings=[],
        average_confidence=99.0,
        timing_ms=10,
    )


def test_process_batch_job_completes_with_mixed_results(monkeypatch) -> None:
    reviews = iter(
        [
            make_review(ReviewStatus.PASS, "Pass row"),
            make_review(ReviewStatus.NEEDS_REVIEW, "Needs review row"),
        ]
    )

    def fake_run_review(*, image_bytes: bytes, application):  # type: ignore[no-untyped-def]
        return next(reviews)

    monkeypatch.setattr(main, "run_review", fake_run_review)

    job_id = "job-mixed"
    main.batch_jobs[job_id] = BatchReviewJobResponse(
        job_id=job_id,
        status=BatchJobStatus.QUEUED,
        total_rows=2,
        processed_rows=0,
        passed=0,
        needs_review=0,
        failed=0,
    )

    main.process_batch_job(
        job_id=job_id,
        rows=[
            {"application_id": "ROW-1", "image_filename": "one.png", "brand_name": "One"},
            {"application_id": "ROW-2", "image_filename": "two.png", "brand_name": "Two"},
        ],
        image_lookup={"one.png": b"1", "two.png": b"2"},
    )

    job = main.batch_jobs[job_id]
    assert job.status == BatchJobStatus.COMPLETED
    assert job.processed_rows == 2
    assert job.passed == 1
    assert job.needs_review == 1
    assert job.failed == 0
    assert len(job.results) == 2

    del main.batch_jobs[job_id]


def test_process_batch_job_marks_missing_image_as_failure(monkeypatch) -> None:
    monkeypatch.setattr(main, "run_review", lambda **_: make_review(ReviewStatus.PASS, "unused"))

    job_id = "job-missing-image"
    main.batch_jobs[job_id] = BatchReviewJobResponse(
        job_id=job_id,
        status=BatchJobStatus.QUEUED,
        total_rows=1,
        processed_rows=0,
        passed=0,
        needs_review=0,
        failed=0,
    )

    main.process_batch_job(
        job_id=job_id,
        rows=[
            {"application_id": "ROW-1", "image_filename": "missing.png", "brand_name": "One"},
        ],
        image_lookup={},
    )

    job = main.batch_jobs[job_id]
    assert job.status == BatchJobStatus.COMPLETED
    assert job.failed == 1
    assert job.results[0].error == "Upload an image file whose name matches image_filename exactly."

    del main.batch_jobs[job_id]
