from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ReviewStatus(str, Enum):
    PASS = "pass"
    NEEDS_REVIEW = "needs_review"
    FAIL = "fail"


class BatchJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ApplicationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(min_length=1)
    class_type: str | None = None
    alcohol_content: str | None = None
    net_contents: str | None = None
    bottler: str | None = None
    country_of_origin: str | None = None
    imported: bool = False


class LabelFields(BaseModel):
    brand_name: str | None = None
    class_type: str | None = None
    alcohol_content: str | None = None
    net_contents: str | None = None
    bottler: str | None = None
    country_of_origin: str | None = None
    government_warning: str | None = None


class FieldReviewResult(BaseModel):
    field: str
    label: str
    expected_value: str | None = None
    detected_value: str | None = None
    status: ReviewStatus
    reason: str


class ReviewResponse(BaseModel):
    overall_status: ReviewStatus
    summary: str
    raw_text: str
    recovered_text: str | None = None
    extracted_fields: LabelFields
    field_results: list[FieldReviewResult]
    preprocessing_notes: list[str]
    warnings: list[str]
    average_confidence: float | None = None
    timing_ms: int


class BatchReviewItem(BaseModel):
    row_number: int
    application_id: str | None = None
    image_filename: str | None = None
    overall_status: ReviewStatus
    summary: str
    field_results: list[FieldReviewResult] = Field(default_factory=list)
    error: str | None = None


class BatchReviewResponse(BaseModel):
    total_rows: int
    passed: int
    needs_review: int
    failed: int
    results: list[BatchReviewItem]


class BatchReviewJobResponse(BaseModel):
    job_id: str
    status: BatchJobStatus
    total_rows: int
    processed_rows: int
    passed: int
    needs_review: int
    failed: int
    results: list[BatchReviewItem] = Field(default_factory=list)
    error: str | None = None


class SingleReviewJobResponse(BaseModel):
    job_id: str
    status: BatchJobStatus
    result: ReviewResponse | None = None
    error: str | None = None
