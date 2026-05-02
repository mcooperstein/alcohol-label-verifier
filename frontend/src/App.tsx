import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from 'react'
import {
  getBatchReviewJob,
  getSingleReviewJob,
  submitBatchReview,
  submitSingleReview,
} from './api'
import './App.css'
import type {
  ApplicationData,
  BatchJobStatus,
  BatchReviewJobResponse,
  FieldReviewResult,
  ReviewResponse,
  ReviewStatus,
  SingleReviewJobResponse,
} from './types'

const initialApplicationData: ApplicationData = {
  brand_name: '',
  class_type: '',
  alcohol_content: '',
  net_contents: '',
  bottler: '',
  country_of_origin: '',
  imported: false,
}

function statusLabel(status: ReviewStatus): string {
  switch (status) {
    case 'pass':
      return 'Pass'
    case 'needs_review':
      return 'Needs Review'
    case 'fail':
      return 'Fail'
  }
}

function batchJobStatusLabel(status: BatchJobStatus): string {
  switch (status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Running'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
  }
}

function App() {
  const [activeView, setActiveView] = useState<'single' | 'batch'>('single')
  const [applicationData, setApplicationData] = useState<ApplicationData>(initialApplicationData)
  const [singleImage, setSingleImage] = useState<File | null>(null)
  const [singleResult, setSingleResult] = useState<ReviewResponse | null>(null)
  const [singleJob, setSingleJob] = useState<SingleReviewJobResponse | null>(null)
  const [singleError, setSingleError] = useState<string>('')
  const [isSubmittingSingle, setIsSubmittingSingle] = useState(false)
  const isSingleRunning = singleJob?.status === 'queued' || singleJob?.status === 'running'

  const [batchCsv, setBatchCsv] = useState<File | null>(null)
  const [batchImages, setBatchImages] = useState<File[]>([])
  const [batchJob, setBatchJob] = useState<BatchReviewJobResponse | null>(null)
  const [batchError, setBatchError] = useState<string>('')
  const [isSubmittingBatch, setIsSubmittingBatch] = useState(false)
  const isBatchRunning = batchJob?.status === 'queued' || batchJob?.status === 'running'

  const selectedImageNames = useMemo(
    () => batchImages.map((file) => file.name).join(', '),
    [batchImages],
  )

  useEffect(() => {
    if (!singleJob || !isSingleRunning) {
      return
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const updatedJob = await getSingleReviewJob(singleJob.job_id)
        setSingleJob(updatedJob)
        if (updatedJob.result) {
          setSingleResult(updatedJob.result)
        }
        if (updatedJob.status === 'failed' && updatedJob.error) {
          setSingleError(updatedJob.error)
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Unable to refresh single review progress.'
        setSingleError(message)
        setSingleJob((current) =>
          current
            ? {
                ...current,
                status: 'failed',
                error: message,
              }
            : current,
        )
      }
    }, 1200)

    return () => window.clearTimeout(timeoutId)
  }, [singleJob, isSingleRunning])

  useEffect(() => {
    if (!batchJob || !isBatchRunning) {
      return
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const updatedJob = await getBatchReviewJob(batchJob.job_id)
        setBatchJob(updatedJob)
        if (updatedJob.status === 'failed' && updatedJob.error) {
          setBatchError(updatedJob.error)
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Unable to refresh batch progress.'
        setBatchError(message)
        setBatchJob((current) =>
          current
            ? {
                ...current,
                status: 'failed',
                error: message,
              }
            : current,
        )
      }
    }, 1200)

    return () => window.clearTimeout(timeoutId)
  }, [batchJob, isBatchRunning])

  const handleInputChange = (
    event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ): void => {
    const { name, value, type } = event.target
    const checked = type === 'checkbox' && 'checked' in event.target ? event.target.checked : false

    setApplicationData((current) => ({
      ...current,
      [name]: type === 'checkbox' ? checked : value,
    }))
  }

  const handleSingleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()

    if (!singleImage) {
      setSingleError('Upload a label image before running a review.')
      return
    }

    setIsSubmittingSingle(true)
    setSingleError('')
    setSingleResult(null)
    setSingleJob(null)

    try {
      const job = await submitSingleReview(singleImage, applicationData)
      setSingleJob(job)
    } catch (error) {
      setSingleResult(null)
      setSingleError(error instanceof Error ? error.message : 'Unable to review the label.')
    } finally {
      setIsSubmittingSingle(false)
    }
  }

  const handleBatchSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()

    if (!batchCsv) {
      setBatchError('Upload a CSV file before running batch review.')
      return
    }

    if (batchImages.length === 0) {
      setBatchError('Upload the label images referenced by the CSV file.')
      return
    }

    setIsSubmittingBatch(true)
    setBatchError('')
    setBatchJob(null)

    try {
      const job = await submitBatchReview(batchCsv, batchImages)
      setBatchJob(job)
    } catch (error) {
      setBatchError(error instanceof Error ? error.message : 'Unable to process the batch.')
    } finally {
      setIsSubmittingBatch(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Standalone compliance prototype</p>
          <h1>Alcohol Label Verification</h1>
          <p className="hero-copy">
            Compare label artwork against application data, flag clear mismatches,
            and route borderline cases to human review.
          </p>
        </div>

        <div className="hero-panel">
          <p className="hero-panel-label">Review outcomes</p>
          <div className="status-preview">
            <StatusBadge status="pass" />
            <StatusBadge status="needs_review" />
            <StatusBadge status="fail" />
          </div>
          <p className="helper-text">
            Designed for fast, explainable review with local OCR and field-level reasons.
          </p>
        </div>
      </header>

      <section className="tabs" aria-label="Review mode">
        <button
          className={activeView === 'single' ? 'tab tab-active' : 'tab'}
          onClick={() => setActiveView('single')}
          type="button"
        >
          Single review
        </button>
        <button
          className={activeView === 'batch' ? 'tab tab-active' : 'tab'}
          onClick={() => setActiveView('batch')}
          type="button"
        >
          Batch review
        </button>
      </section>

      {activeView === 'single' ? (
        <section className="panel-grid">
          <form className="panel" onSubmit={handleSingleSubmit}>
            <div className="panel-header">
              <h2>Application data</h2>
              <p>Enter the expected values and upload one label image.</p>
            </div>

            <label className="field">
              <span>Label image</span>
              <input
                accept="image/*"
                onChange={(event) => setSingleImage(event.target.files?.[0] ?? null)}
                type="file"
              />
            </label>

            <div className="field-grid">
              <label className="field">
                <span>Brand name *</span>
                <input
                  name="brand_name"
                  onChange={handleInputChange}
                  required
                  type="text"
                  value={applicationData.brand_name}
                />
              </label>

              <label className="field">
                <span>Class / type</span>
                <input
                  name="class_type"
                  onChange={handleInputChange}
                  type="text"
                  value={applicationData.class_type}
                />
              </label>

              <label className="field">
                <span>Alcohol content</span>
                <input
                  name="alcohol_content"
                  onChange={handleInputChange}
                  placeholder="45% Alc./Vol. (90 Proof)"
                  type="text"
                  value={applicationData.alcohol_content}
                />
              </label>

              <label className="field">
                <span>Net contents</span>
                <input
                  name="net_contents"
                  onChange={handleInputChange}
                  placeholder="750 mL"
                  type="text"
                  value={applicationData.net_contents}
                />
              </label>

              <label className="field field-wide">
                <span>Bottler / producer</span>
                <input
                  name="bottler"
                  onChange={handleInputChange}
                  type="text"
                  value={applicationData.bottler}
                />
              </label>

              <label className="checkbox-field">
                <input
                  checked={applicationData.imported}
                  name="imported"
                  onChange={handleInputChange}
                  type="checkbox"
                />
                <span>This is an imported product</span>
              </label>

              <label className="field">
                <span>Country of origin</span>
                <input
                  name="country_of_origin"
                  onChange={handleInputChange}
                  placeholder="Required for imports"
                  type="text"
                  value={applicationData.country_of_origin}
                />
              </label>
            </div>

            {singleError ? <p className="error-banner">{singleError}</p> : null}

            <button className="primary-button" disabled={isSubmittingSingle || isSingleRunning} type="submit">
              {isSubmittingSingle
                ? 'Starting review...'
                : isSingleRunning
                  ? 'Review in progress...'
                  : 'Run review'}
            </button>
          </form>

          <section className="panel">
            <div className="panel-header">
              <h2>Review result</h2>
              <p>Field-by-field results explain what matched and what needs attention.</p>
            </div>

            {singleJob ? (
              <div className="summary-card">
                <div className="summary-header batch-progress-header">
                  <p className="progress-copy">
                    <strong>{batchJobStatusLabel(singleJob.status)}</strong>
                    {singleJob.status === 'completed'
                      ? ' - review finished.'
                      : ' - label review is processing in the background.'}
                  </p>
                </div>
              </div>
            ) : null}

            {singleResult ? (
              <>
                <ResultSummary result={singleResult} />
                <FieldResultsTable fieldResults={singleResult.field_results} />

                <div className="meta-grid">
                  <div className="meta-card">
                    <h3>Processing details</h3>
                    <dl>
                      <div>
                        <dt>Latency</dt>
                        <dd>{singleResult.timing_ms} ms</dd>
                      </div>
                      <div>
                        <dt>Average OCR confidence</dt>
                        <dd>
                          {singleResult.average_confidence === null
                            ? 'Unavailable'
                            : `${singleResult.average_confidence}%`}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  <div className="meta-card">
                    <h3>Preprocessing</h3>
                    <ul>
                      {singleResult.preprocessing_notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {singleResult.warnings.length > 0 ? (
                  <div className="meta-card warning-card">
                    <h3>Warnings</h3>
                    <ul>
                      {singleResult.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {singleResult.recovered_text ? (
                  <div className="text-card">
                    <h3>Likely recovered text</h3>
                    <pre>{singleResult.recovered_text}</pre>
                  </div>
                ) : null}

                <div className="text-card">
                  <h3>Extracted text</h3>
                  <pre>{singleResult.raw_text || 'No text was extracted.'}</pre>
                </div>
              </>
            ) : singleJob ? (
              <div className="empty-state">
                <h3>Review queued</h3>
                <p>The label review is running in the background. Results will appear here automatically.</p>
              </div>
            ) : (
              <div className="empty-state">
                <h3>No review yet</h3>
                <p>Run a single-label review to see extracted text, match reasons, and the final status.</p>
              </div>
            )}
          </section>
        </section>
      ) : (
        <section className="panel-grid panel-grid-single">
          <form className="panel" onSubmit={handleBatchSubmit}>
            <div className="panel-header">
              <h2>Batch inputs</h2>
              <p>
                Upload a CSV file plus the corresponding label images. Image filenames must
                match the <code>image_filename</code> column exactly.
              </p>
            </div>

            <label className="field">
              <span>Batch CSV</span>
              <input
                accept=".csv,text/csv"
                onChange={(event) => setBatchCsv(event.target.files?.[0] ?? null)}
                type="file"
              />
            </label>

            <label className="field">
              <span>Label images</span>
              <input
                accept="image/*"
                multiple
                onChange={(event) => setBatchImages(Array.from(event.target.files ?? []))}
                type="file"
              />
            </label>

            {selectedImageNames ? <p className="helper-text">{selectedImageNames}</p> : null}
            {batchError ? <p className="error-banner">{batchError}</p> : null}

            <button className="primary-button" disabled={isSubmittingBatch || isBatchRunning} type="submit">
              {isSubmittingBatch
                ? 'Starting batch review...'
                : isBatchRunning
                  ? 'Batch review in progress...'
                  : 'Run batch review'}
            </button>
          </form>

          <section className="panel">
            <div className="panel-header">
              <h2>Batch results</h2>
              <p>Review statuses are grouped by row so reviewers can quickly triage the queue.</p>
            </div>

            {batchJob ? (
              <>
                <div className="summary-card">
                  <div className="summary-header batch-progress-header">
                    <p className="progress-copy">
                      <strong>{batchJobStatusLabel(batchJob.status)}</strong> - processed{' '}
                      {batchJob.processed_rows} of {batchJob.total_rows} rows
                    </p>
                    <p className="progress-copy">
                      {isBatchRunning
                        ? 'Rows are being processed in the background to avoid host timeouts.'
                        : 'Batch processing finished.'}
                    </p>
                  </div>
                </div>

                <div className="batch-summary-grid">
                  <SummaryStat label="Rows" value={String(batchJob.total_rows)} />
                  <SummaryStat label="Processed" value={String(batchJob.processed_rows)} />
                  <SummaryStat label="Pass" value={String(batchJob.passed)} />
                  <SummaryStat label="Needs Review" value={String(batchJob.needs_review)} />
                  <SummaryStat label="Fail" value={String(batchJob.failed)} />
                </div>

                <div className="table-wrapper">
                  <table>
                    <thead>
                      <tr>
                        <th>Row</th>
                        <th>Application</th>
                        <th>Image</th>
                        <th>Status</th>
                        <th>Summary</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batchJob.results.map((item) => (
                        <tr key={`${item.row_number}-${item.image_filename ?? 'missing'}`}>
                          <td>{item.row_number}</td>
                          <td>{item.application_id ?? '—'}</td>
                          <td>{item.image_filename ?? '—'}</td>
                          <td>
                            <StatusBadge status={item.overall_status} />
                          </td>
                          <td>{item.error ?? item.summary}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <h3>No batch results yet</h3>
                <p>Upload a CSV and matching images to process a high-volume review set.</p>
              </div>
            )}
          </section>
        </section>
      )}
    </main>
  )
}

function ResultSummary({ result }: { result: ReviewResponse }) {
  return (
    <section className="summary-card">
      <div className="summary-header">
        <StatusBadge status={result.overall_status} />
        <p>{result.summary}</p>
      </div>
    </section>
  )
}

function FieldResultsTable({ fieldResults }: { fieldResults: FieldReviewResult[] }) {
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Expected</th>
            <th>Detected</th>
            <th>Status</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {fieldResults.map((result) => (
            <tr key={result.field}>
              <td>{result.label}</td>
              <td>{result.expected_value ?? '—'}</td>
              <td>{result.detected_value ?? '—'}</td>
              <td>
                <StatusBadge status={result.status} />
              </td>
              <td>{result.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function StatusBadge({ status }: { status: ReviewStatus }) {
  return <span className={`status-badge status-${status}`}>{statusLabel(status)}</span>
}

export default App
