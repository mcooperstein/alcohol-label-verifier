export type ReviewStatus = 'pass' | 'needs_review' | 'fail'
export type BatchJobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface ApplicationData {
  brand_name: string
  class_type: string
  alcohol_content: string
  net_contents: string
  bottler: string
  country_of_origin: string
  imported: boolean
}

export interface LabelFields {
  brand_name: string | null
  class_type: string | null
  alcohol_content: string | null
  net_contents: string | null
  bottler: string | null
  country_of_origin: string | null
  government_warning: string | null
}

export interface FieldReviewResult {
  field: string
  label: string
  expected_value: string | null
  detected_value: string | null
  status: ReviewStatus
  reason: string
}

export interface ReviewResponse {
  overall_status: ReviewStatus
  summary: string
  raw_text: string
  extracted_fields: LabelFields
  field_results: FieldReviewResult[]
  preprocessing_notes: string[]
  warnings: string[]
  average_confidence: number | null
  timing_ms: number
}

export interface BatchReviewItem {
  row_number: number
  application_id: string | null
  image_filename: string | null
  overall_status: ReviewStatus
  summary: string
  field_results: FieldReviewResult[]
  error: string | null
}

export interface BatchReviewResponse {
  total_rows: number
  passed: number
  needs_review: number
  failed: number
  results: BatchReviewItem[]
}

export interface BatchReviewJobResponse {
  job_id: string
  status: BatchJobStatus
  total_rows: number
  processed_rows: number
  passed: number
  needs_review: number
  failed: number
  results: BatchReviewItem[]
  error: string | null
}

export interface SingleReviewJobResponse {
  job_id: string
  status: BatchJobStatus
  result: ReviewResponse | null
  error: string | null
}
