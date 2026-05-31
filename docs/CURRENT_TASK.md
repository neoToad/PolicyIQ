# Current Task

**Step**: 2.4 — De-duplicate citation construction
**Status**: Starting
**What I'm doing**: Extracting the duplicated `citations` list-comprehension from `AskPageView.post()` and `QueryAPIView.post()` into a shared `build_citations()` helper in `queries/services/`

**Blockers/Decisions**: None

**Next step**: 2.5 — Decouple `retriever.py` from `documents.models`
