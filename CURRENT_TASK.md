# Current Task

**Step 2.3 — Generator**

Building queries/services/generator.py for PolicyIQ.

- Adding generate_response(prompt: str) generator function that:
  - Calls Ollama generate API at http://localhost:11434/api/generate with llama3.2
  - Streams response line by line via equests with stream=True
  - Parses each JSON line and yields the esponse field
  - Raises a clear exception if Ollama is unreachable

Next: 2.4 — Query View.
