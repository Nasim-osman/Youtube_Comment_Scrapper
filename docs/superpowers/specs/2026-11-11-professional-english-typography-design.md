# Professional English UI and Typography Design

**Date:** 2026-11-11
**Status:** Approved for spec review

## Goal

Give the login and extraction pages consistent professional English copy and updated typography without changing the app's layout, colors, authentication, extraction, or history behavior.

## User experience

- The login page displays: “Welcome to Nasim’s personal YouTube comment scraper site.”
- All app-authored, user-visible copy on the login and extraction pages is in professional English, including labels, buttons, hints, empty states, image alternatives, login feedback, and extraction/database errors.
- Both pages declare English as their document language and use the same modern system sans-serif font stack.
- Existing page layout, visual styling, and application behavior remain unchanged.

## Scope

- Update `templates/login.html` and `templates/index.html` for the English document language, consistent system typography, and professional English interface text.
- Update app-authored login, extraction, and history messages in `app.py` and validation/configuration messages surfaced from `comments.py`.
- Preserve authentication, CSRF checks, extraction flow, workbook output, history persistence, and routes.
- Do not translate technical documentation or change non-user-facing source comments.

## Validation

- Run the existing app tests and update expectations for translated visible messages.
- Verify the login welcome heading and all static interface labels render in English.
- Verify representative login, invalid-input, and extraction error messages render in English.
- Verify login, extraction/download, and history behavior remain unchanged.
