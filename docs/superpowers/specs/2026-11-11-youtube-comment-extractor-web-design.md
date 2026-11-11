# YouTube Comment Extractor Web App Design

**Date:** 2026-11-11
**Status:** Approved for spec review

## Goal

Turn the existing YouTube comment extractor into a private, Render-hosted web app. The user submits a video URL, downloads an Excel workbook, and can revisit a history of successfully processed video URLs and thumbnails.

## User experience

1. The user opens the app and enters its configured password.
2. The home page accepts a YouTube video URL and shows prior extraction history, with a video thumbnail and URL for each successful run.
3. After submission, the app extracts comments and replies and returns the generated Excel workbook as a browser download.
4. The app does not retain comment text or workbook files. History records contain only the video ID, its canonical YouTube URL, thumbnail URL, and extraction timestamp. Each successful run creates a history entry, including repeated runs of the same video.

## Architecture

- **Web app:** Flask, with the current Python extractor refactored into an import-safe function called by the request handler.
- **Hosting:** One Render web service and a Render PostgreSQL database for durable history.
- **Authentication:** One app password configured by the owner; successful login is maintained with a protected session.
- **Configuration:** Read the YouTube API key, app password, Flask session secret, and database URL from environment variables. Do not place secrets in source code. Rotate the API key currently embedded in the script before deploying it.
- **History:** Store only video ID, canonical YouTube URL, thumbnail URL, and timestamp. Show the thumbnail and URL in the UI; do not store comments or Excel files.
- **Workbook delivery:** Build the workbook in memory and return it as an attachment, avoiding persistent export files.

## Extraction and Excel compatibility

The existing extraction algorithm remains the source of truth: request comment threads in time order, include all available replies, and preserve the current row ordering and values. The submitted URL replaces the hardcoded URL.

Preserve the workbook's current filename convention (sanitized video title plus `.xlsx`), six columns and their order (`Type`, `Author`, `Comment`, `Replying_To`, `Likes`, `Published_At`), column widths, blue header styling, and wrapped cell formatting. Do not change comment collection behavior or workbook layout as part of the web-app work.

The video details request also supplies the thumbnail URL for the history entry. Only make a history entry for a completed extraction with a generated workbook.

## Error behavior

Reject invalid or unsupported YouTube URLs before extraction. If comments are disabled/unavailable, the API key or quota fails, extraction fails, or the database cannot save history, show a clear error rather than returning a success-shaped or partial workbook. Do not silently hide reply-fetch failures. Do not add a history record for a failed extraction.

## Scope and known limitation

This version is a single-user app with synchronous extraction and a compact history; it has no user accounts, comment browser, search, or saved Excel downloads. Very large videos may take longer than a hosting request allows. If this occurs in practice, background jobs and temporary download storage can be designed as a separate follow-up without changing the workbook format.

## Validation

- Verify valid YouTube URL forms are accepted and invalid URLs fail clearly.
- Test that extraction uses the submitted video and preserves comment/reply ordering.
- Verify the generated workbook's filename, column names/order, representative data, widths, header style, and cell wrapping match the current script.
- Verify password protection, successful-history insertion, thumbnail rendering, and history persistence across app restarts.
- Verify failed extraction or persistence reports an error and does not create a history item or partial workbook.
- Verify no comment text or workbook file is written to the history database or persistent filesystem.
