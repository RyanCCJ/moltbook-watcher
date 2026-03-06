## MODIFIED Requirements

### Requirement: Translation language configurable via TRANSLATION_LANGUAGE

The system SHALL read the `TRANSLATION_LANGUAGE` environment variable to determine the target language for content translation. When `TRANSLATION_LANGUAGE` is empty (default), the system SHALL skip all translation and store original text as-is. When set to a language code (e.g., `zh`, `ja`, `ko`), the system SHALL translate content to that language using Ollama.

The translation mechanism SHALL use a batch JSON-structured prompt (via `_translate_batch`) to translate the post content and all top comments in a single Ollama call, instead of making individual translation calls for each item. If the batch call fails, the system SHALL fall back to individual `_translate()` calls per item.

#### Scenario: TRANSLATION_LANGUAGE is empty (default)

- **WHEN** `TRANSLATION_LANGUAGE` is not set or is an empty string
- **THEN** the `ReviewPayloadService` skips all translation calls (including batch), stores the original `raw_content` in the translation field, and stores empty lists for `top_comments_translated`

#### Scenario: TRANSLATION_LANGUAGE is set to zh-TW

- **WHEN** `TRANSLATION_LANGUAGE=zh-TW`
- **THEN** the `ReviewPayloadService` translates the post content and top comments to Traditional Chinese (Taiwan) via a single batch Ollama call and stores the translated versions in their respective fields

#### Scenario: TRANSLATION_LANGUAGE is set to an unsupported or unusual code

- **WHEN** `TRANSLATION_LANGUAGE` is set to an arbitrary language code (e.g., `pt-BR`)
- **THEN** the system passes the code to the Ollama batch translation prompt and trusts the model to translate accordingly — no client-side language code validation is performed

#### Scenario: Batch translation fails, falls back to sequential

- **WHEN** `TRANSLATION_LANGUAGE=zh-TW` and the batch Ollama call returns invalid JSON
- **THEN** the system falls back to individual `_translate()` calls for the content and each comment, producing the same output as the pre-batch behavior
