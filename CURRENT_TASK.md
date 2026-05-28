# Current Task

**Step 2.2 — Prompt Builder**

Building queries/services/generator.py for PolicyIQ.

- Implementing uild_prompt(question, chunks, similarity_threshold) that:
  - Checks if highest similarity score clears the threshold
  - Returns None if no chunk is relevant enough
  - Builds a grounded prompt string with document name + page number per chunk
  - Instructs the LLM to answer only from provided context

Next: 2.3 — Generator.
