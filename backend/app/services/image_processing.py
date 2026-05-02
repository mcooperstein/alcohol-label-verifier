from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

MIN_OCR_DIMENSION = 1400
MAX_OCR_DIMENSION = 2200


def preprocess_image(image_bytes: bytes) -> tuple[np.ndarray, list[str], list[tuple[str, np.ndarray]]]:
    image = None
    try:
        with Image.open(BytesIO(image_bytes)) as pil_image:
            corrected_image = ImageOps.exif_transpose(pil_image).convert("RGB")
            image = cv2.cvtColor(np.array(corrected_image), cv2.COLOR_RGB2BGR)
    except Exception:
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("The uploaded file could not be decoded as an image.")

    notes: list[str] = []
    height, width = image.shape[:2]

    if max(height, width) > MAX_OCR_DIMENSION:
        scale = MAX_OCR_DIMENSION / max(height, width)
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        notes.append("Downscaled a large source image to improve OCR speed and stability.")

    if max(height, width) < MIN_OCR_DIMENSION:
        scale = MIN_OCR_DIMENSION / max(height, width)
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        notes.append("Upscaled a small source image to improve OCR readability.")

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(grayscale, h=15)
    boosted = cv2.convertScaleAbs(denoised, alpha=1.2, beta=10)
    thresholded = cv2.adaptiveThreshold(
        boosted,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    notes.append("Applied grayscale, denoising, contrast boost, and adaptive thresholding.")
    alternate_images = [("boosted grayscale", boosted)]
    return thresholded, notes, alternate_images
