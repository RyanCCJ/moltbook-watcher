## ADDED Requirements

### Requirement: Batch translation via JSON-structured prompt

The `ReviewPayloadService` SHALL provide a `_translate_batch` method that translates post content and up to 5 top comments in a single Ollama LLM call. The method SHALL construct a JSON object with keys `content`, `comment_1`, `comment_2`, … `comment_N` as input, and expect a JSON object with the same keys as output, each value being the translated text.

#### Scenario: Batch translation with content and 3 comments

- **WHEN** `_translate_batch` is called with post content and 3 comments
- **THEN** the method sends one Ollama request with a JSON input containing keys `content`, `comment_1`, `comment_2`, `comment_3`, and returns a tuple of (translated_content, translated_comments_list) parsed from the response JSON

#### Scenario: Batch translation with content only (no comments)

- **WHEN** `_translate_batch` is called with post content and an empty comments list
- **THEN** the method sends one Ollama request with a JSON input containing only the key `content`, and returns (translated_content, [])

#### Scenario: Batch translation with a comment that has empty content

- **WHEN** one of the comments has an empty `content_text`
- **THEN** the method SHALL skip that comment in the JSON input (do not include the key) and return an empty string for that comment's translation in the output list

### Requirement: Batch translation uses response_format schema

The batch translation Ollama call SHALL include a `response_format` (via the `format` parameter) that dynamically defines the expected JSON schema based on the input keys. All input keys SHALL be listed as `required` in the schema.

#### Scenario: Schema matches input keys

- **WHEN** the input JSON has keys `content`, `comment_1`, `comment_2`
- **THEN** the `format` parameter sent to Ollama contains a JSON schema with properties `content`, `comment_1`, `comment_2`, all typed as `string` and all listed in `required`

### Requirement: Batch translation fallback to sequential

If the batch translation call fails (Ollama error, JSON parse failure, or missing keys in response), the system SHALL fall back to sequential per-item `_translate()` calls for the content and each comment individually.

#### Scenario: Ollama returns invalid JSON

- **WHEN** the batch translation Ollama call returns a response that cannot be parsed as a valid JSON object
- **THEN** the system logs a warning and falls back to calling `_translate(content)` and `_translate(comment)` individually for each item

#### Scenario: Ollama returns JSON with missing keys

- **WHEN** the batch translation response JSON is missing the `content` key
- **THEN** the system treats the batch as failed and falls back to sequential translation

#### Scenario: Ollama HTTP error

- **WHEN** the batch translation Ollama call raises an `httpx.HTTPError`
- **THEN** the system logs a warning, disables Ollama (`_ollama_enabled = False`), and returns empty translations (consistent with existing fallback behavior)

### Requirement: build_payload uses batch translation

The `build_payload` method SHALL call `_translate_batch` instead of separate `_translate` and `_translate_comments` calls when `_translation_language` is set. The existing `_translate` and `_translate_comments` methods SHALL be preserved for fallback use and backward compatibility.

#### Scenario: build_payload with translation enabled

- **WHEN** `build_payload` is called with `_translation_language` set to a non-empty value
- **THEN** the method calls `_translate_batch(raw_content, top_comments, target_language)` and uses the returned tuple for `chinese_translation_full` and `top_comments_translated`

#### Scenario: build_payload with translation disabled

- **WHEN** `build_payload` is called with `_translation_language` set to empty string
- **THEN** the method skips all translation calls (same as current behavior) and returns empty translation fields
