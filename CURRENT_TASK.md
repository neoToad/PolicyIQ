# Current Task

**Step 4.1 — Multi-Document Upload**

Updating the upload view and form to support multiple PDFs at once.

- Added `multiple` attribute to the file input in `templates/documents/upload.html`
- Updated `UploadPageView.post()` to process `request.FILES.getlist("file")` sequentially
- Each file is ingested independently; failures are captured per file without stopping the batch
- Updated `_upload_result.html` to display a summary of all results with per-file status
- Also updated `DocumentUploadAPIView` to support multiple files for API parity

Next: 4.2 — Similarity Score Indicator.