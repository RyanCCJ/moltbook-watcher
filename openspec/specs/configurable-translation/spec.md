# Capability: Configurable Translation

## Purpose
Allow users to configure the target language for content translation and Threads draft generation via environment variables.

## Requirements

### Requirement: Translation language configurable via TRANSLATION_LANGUAGE

The system SHALL read the `TRANSLATION_LANGUAGE` environment variable to determine the target language for content translation. When `TRANSLATION_LANGUAGE` is empty (default), the system SHALL skip all translation and store original text as-is. When set to a language code (e.g., `zh`, `ja`, `ko`), the system SHALL translate content to that language using Ollama.

#### Scenario: TRANSLATION_LANGUAGE is empty (default)

- **WHEN** `TRANSLATION_LANGUAGE` is not set or is an empty string
- **THEN** the `ReviewPayloadService` skips translation calls to Ollama, stores the original `raw_content` in the translation field, and stores empty lists for `top_comments_translated`

#### Scenario: TRANSLATION_LANGUAGE is set to zh-TW

- **WHEN** `TRANSLATION_LANGUAGE=zh-TW`
- **THEN** the `ReviewPayloadService` translates the post content and top comments to Traditional Chinese (Taiwan) via Ollama and stores the translated versions in their respective fields

#### Scenario: TRANSLATION_LANGUAGE is set to an unsupported or unusual code

- **WHEN** `TRANSLATION_LANGUAGE` is set to an arbitrary language code (e.g., `pt-BR`)
- **THEN** the system passes the code to the Ollama translation prompt and trusts the model to translate accordingly — no client-side language code validation is performed

### Requirement: Threads draft language configurable via THREADS_LANGUAGE

The system SHALL read the `THREADS_LANGUAGE` environment variable to determine the language for auto-generated Threads drafts. The default value SHALL be `en` (English). This setting is independent from `TRANSLATION_LANGUAGE`.

#### Scenario: THREADS_LANGUAGE uses default value

- **WHEN** `THREADS_LANGUAGE` is not set in the environment
- **THEN** the system uses `en` as the default and generates Threads drafts in English

#### Scenario: THREADS_LANGUAGE set to a different language

- **WHEN** `THREADS_LANGUAGE=ja`
- **THEN** the Threads draft generation prompt instructs Ollama to write in Japanese

#### Scenario: Independent from TRANSLATION_LANGUAGE

- **WHEN** `TRANSLATION_LANGUAGE=zh-TW` and `THREADS_LANGUAGE=en`
- **THEN** review translations are in Traditional Chinese but the Threads draft is in English — the two settings do not affect each other

### Requirement: Settings model includes language configuration

The `Settings` class in `src/config/settings.py` SHALL include two new fields: `translation_language: str` (default `""`) and `threads_language: str` (default `"en"`), both read from their respective environment variables.

#### Scenario: Settings loaded with both variables set

- **WHEN** the environment contains `TRANSLATION_LANGUAGE=zh-TW` and `THREADS_LANGUAGE=en`
- **THEN** `Settings.translation_language` equals `"zh-TW"` and `Settings.threads_language` equals `"en"`

#### Scenario: Settings loaded with no language variables

- **WHEN** neither `TRANSLATION_LANGUAGE` nor `THREADS_LANGUAGE` is set in the environment
- **THEN** `Settings.translation_language` equals `""` and `Settings.threads_language` equals `"en"`

### Requirement: Translation prompt adapts to configured language

When `TRANSLATION_LANGUAGE` is set, the Ollama translation prompt SHALL specify the exact target language name (derived from the language code) instead of being hardcoded to "Traditional Chinese."

#### Scenario: Translation to Traditional Chinese

- **WHEN** `TRANSLATION_LANGUAGE=zh-TW`
- **THEN** the Ollama prompt instructs translation into "Traditional Chinese (Taiwan usage)"

#### Scenario: Translation to Japanese

- **WHEN** `TRANSLATION_LANGUAGE=ja`
- **THEN** the Ollama prompt instructs translation into "Japanese"

### Requirement: env.example and documentation updated

The `.env.example` file SHALL include `TRANSLATION_LANGUAGE` and `THREADS_LANGUAGE` with descriptive comments. The README and relevant docs SHALL document the new settings, their defaults, and the breaking change to translation behavior.

#### Scenario: env.example contains new variables

- **WHEN** a developer copies `.env.example` to `.env`
- **THEN** they see `TRANSLATION_LANGUAGE=` (empty default) and `THREADS_LANGUAGE=en` with comments explaining the purpose and valid values

#### Scenario: README documents breaking change

- **WHEN** a user reads the README after upgrading
- **THEN** they find a note explaining that translation is no longer automatic by default and instructions to set `TRANSLATION_LANGUAGE=zh-TW` to restore previous behavior
