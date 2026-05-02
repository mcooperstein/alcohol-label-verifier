import type {
  ApplicationData,
  BatchReviewJobResponse,
  SingleReviewJobResponse,
} from './types'

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T
  }

  let detail = 'The request could not be completed.'

  try {
    const errorBody = (await response.json()) as { detail?: string | { msg?: string }[] }
    if (typeof errorBody.detail === 'string') {
      detail = errorBody.detail
    } else if (Array.isArray(errorBody.detail) && errorBody.detail.length > 0) {
      detail = errorBody.detail.map((item) => item.msg ?? 'Validation error').join(', ')
    }
  } catch {
    // Fall back to the default message when the response is not JSON.
  }

  throw new Error(detail)
}

export async function submitSingleReview(
  image: File,
  applicationData: ApplicationData,
): Promise<SingleReviewJobResponse> {
  const formData = new FormData()
  formData.append('label_image', image)
  formData.append('application_data', JSON.stringify(applicationData))

  const response = await fetch('/api/review-jobs', {
    method: 'POST',
    body: formData,
  })

  return parseResponse<SingleReviewJobResponse>(response)
}

export async function getSingleReviewJob(jobId: string): Promise<SingleReviewJobResponse> {
  const response = await fetch(`/api/review-jobs/${jobId}`)
  return parseResponse<SingleReviewJobResponse>(response)
}

export async function submitBatchReview(
  csvFile: File,
  images: File[],
): Promise<BatchReviewJobResponse> {
  const formData = new FormData()
  formData.append('csv_file', csvFile)
  images.forEach((image) => {
    formData.append('images', image)
  })

  const response = await fetch('/api/batch-review-jobs', {
    method: 'POST',
    body: formData,
  })

  return parseResponse<BatchReviewJobResponse>(response)
}

export async function getBatchReviewJob(jobId: string): Promise<BatchReviewJobResponse> {
  const response = await fetch(`/api/batch-review-jobs/${jobId}`)
  return parseResponse<BatchReviewJobResponse>(response)
}
