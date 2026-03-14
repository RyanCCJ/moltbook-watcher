## MODIFIED Requirements

### Requirement: Draft generation fails

- **WHEN** Ollama returns an error or empty response during draft generation
- **THEN** the system logs a warning, sets `threads_draft` to an empty string, and continues without failing the review item creation. If the error is an `httpx.HTTPError`, the system SHALL increment the consecutive failure counter. Ollama SHALL only be disabled (`_ollama_enabled = False`) when the consecutive failure counter reaches the configured threshold (default: 3). Non-HTTP errors (e.g., empty response, content too similar to source) SHALL NOT increment the failure counter.

#### Scenario: First httpx timeout during draft generation

- **WHEN** `_generate_threads_draft()` raises an `httpx.ReadTimeout` and the consecutive failure counter is 0
- **THEN** the system logs a warning, increments the consecutive failure counter to 1, sets `threads_draft` to an empty string, and continues processing subsequent items with Ollama still enabled

#### Scenario: Third consecutive httpx failure triggers disable

- **WHEN** `_generate_threads_draft()` raises an `httpx.HTTPError` and the consecutive failure counter is already at 2 (making this the third consecutive failure)
- **THEN** the system logs a warning, sets `_ollama_enabled = False`, and all subsequent Ollama calls in this service instance return empty results

#### Scenario: Successful call resets failure counter

- **WHEN** a draft generation or translation call completes successfully after one or two prior failures
- **THEN** the consecutive failure counter SHALL be reset to 0

#### Scenario: Non-HTTP error does not count toward circuit breaker

- **WHEN** draft generation produces an empty response or a near-copy of the source (non-HTTP error)
- **THEN** the system returns an empty string but does NOT increment the consecutive failure counter

### Requirement: Configurable Ollama timeout

The `ReviewPayloadService` httpx client timeout SHALL be configurable via the `OLLAMA_TIMEOUT_SECONDS` environment variable (default: 300). The same setting SHALL also be used by `ScoringService`. The hardcoded 180s timeout in `ReviewPayloadService` and the 60s timeout in `ScoringService` SHALL be replaced by this single configurable value.

#### Scenario: Default timeout applied

- **WHEN** `OLLAMA_TIMEOUT_SECONDS` is not set in the environment
- **THEN** both `ReviewPayloadService` and `ScoringService` SHALL use a 300-second httpx timeout

#### Scenario: Custom timeout applied

- **WHEN** `OLLAMA_TIMEOUT_SECONDS=600` is set in the environment
- **THEN** both `ReviewPayloadService` and `ScoringService` SHALL use a 600-second httpx timeout

#### Scenario: Minimum timeout enforced

- **WHEN** `OLLAMA_TIMEOUT_SECONDS` is set to a value below 30
- **THEN** the system SHALL reject the value at startup with a validation error
