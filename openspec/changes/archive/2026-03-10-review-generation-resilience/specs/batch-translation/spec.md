## MODIFIED Requirements

### Requirement: Batch translation fallback to sequential

If the batch translation call fails (Ollama error, JSON parse failure, or missing keys in response), the system SHALL fall back to sequential per-item `_translate()` calls for the content and each comment individually. If the error is an `httpx.HTTPError`, the system SHALL increment the consecutive failure counter shared with `_generate_threads_draft` and `_translate`. Ollama SHALL only be disabled when the consecutive failure counter reaches the configured threshold (default: 3). JSON parse failures and missing-key errors SHALL NOT increment the failure counter because they indicate model output issues rather than connectivity problems.

#### Scenario: Ollama returns invalid JSON

- **WHEN** the batch translation Ollama call returns a response that cannot be parsed as a valid JSON object
- **THEN** the system logs a warning and falls back to calling `_translate(content)` and `_translate(comment)` individually for each item. The consecutive failure counter SHALL NOT be incremented.

#### Scenario: Ollama returns JSON with missing keys

- **WHEN** the batch translation response JSON is missing the `content` key
- **THEN** the system treats the batch as failed, falls back to sequential translation, and does NOT increment the consecutive failure counter

#### Scenario: Ollama HTTP error

- **WHEN** the batch translation Ollama call raises an `httpx.HTTPError` and the consecutive failure counter has not yet reached the threshold
- **THEN** the system logs a warning, increments the consecutive failure counter, falls back to sequential translation (which may also fail if Ollama is truly unreachable), and continues processing

#### Scenario: Ollama HTTP error reaches threshold

- **WHEN** the batch translation Ollama call raises an `httpx.HTTPError` and the consecutive failure counter reaches the configured threshold (default: 3)
- **THEN** the system disables Ollama (`_ollama_enabled = False`) and returns empty translations for the current and all subsequent items
