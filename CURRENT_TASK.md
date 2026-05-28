# Current Task

**Step 3.2 — Upload Form**

Building the HTMX upload form and updating the upload view for PolicyIQ.

- Rewriting `templates/documents/upload.html` with HTMX file upload form
- Adding `templates/documents/_upload_result.html` partial for success/error feedback
- Updating `UploadPageView` to handle POST and return HTML partials
- Refactoring ingestion pipeline into `_save_upload_and_ingest()` shared by page view and API view

Next: 3.3 — Upload History.