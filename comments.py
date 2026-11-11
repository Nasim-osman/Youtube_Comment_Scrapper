import html
import os
import re
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import openpyxl
import pandas as pd
from googleapiclient.discovery import build
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = ["Type", "Author", "Comment", "Replying_To", "Likes", "Published_At"]
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass
class ExtractionResult:
    video_id: str
    video_url: str
    title: str
    thumbnail_url: str
    filename: str
    workbook: BytesIO


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sanitize_filename(name):
    clean_name = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean_name.strip()


def get_video_id(url_or_id):
    value = url_or_id.strip()
    if VIDEO_ID_PATTERN.fullmatch(value):
        return value

    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    video_id = None

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Enter a valid YouTube video URL.")

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        else:
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) == 2 and path_parts[0] in {"shorts", "embed", "live"}:
                video_id = path_parts[1]
    elif host in {"youtu.be", "www.youtu.be"}:
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) == 1:
            video_id = path_parts[0]

    if not video_id or not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError("Enter a valid YouTube video URL.")
    return video_id


def create_youtube_client(api_key=None):
    api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("The YouTube API key is not configured on the server.")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def get_video_metadata(youtube, video_id):
    response = youtube.videos().list(part="snippet", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        raise ValueError("The video could not be found or accessed.")

    snippet = items[0].get("snippet", {})
    title = clean_text(snippet.get("title", "")) or video_id
    thumbnails = snippet.get("thumbnails", {})
    thumbnail_url = next(
        (
            thumbnails[name]["url"]
            for name in ("maxres", "standard", "high", "medium", "default")
            if thumbnails.get(name, {}).get("url")
        ),
        "",
    )
    return title, thumbnail_url


def fetch_all_replies(youtube, parent_id, parent_author):
    replies_data = []
    next_reply_token = None

    while True:
        reply_response = (
            youtube.comments()
            .list(
                part="snippet",
                parentId=parent_id,
                maxResults=100,
                pageToken=next_reply_token,
                textFormat="plainText",
            )
            .execute()
        )

        for reply_item in reply_response.get("items", []):
            snippet = reply_item["snippet"]
            replies_data.append(
                {
                    "Type": "REPLY",
                    "Author": clean_text(snippet.get("authorDisplayName", "")),
                    "Comment": clean_text(snippet.get("textDisplay", "")),
                    "Replying_To": parent_author,
                    "Likes": snippet.get("likeCount", 0),
                    "Published_At": snippet.get("publishedAt", ""),
                }
            )

        next_reply_token = reply_response.get("nextPageToken")
        if not next_reply_token:
            break

    return replies_data


def fetch_comments(youtube, video_id):
    comments_data = []
    next_page_token = None

    while True:
        response = (
            youtube.commentThreads()
            .list(
                part="snippet,replies",
                videoId=video_id,
                order="time",
                maxResults=100,
                pageToken=next_page_token,
                textFormat="plainText",
            )
            .execute()
        )

        for item in response.get("items", []):
            thread = item["snippet"]
            top_comment = thread["topLevelComment"]["snippet"]
            parent_id = thread["topLevelComment"]["id"]
            total_replies = thread.get("totalReplyCount", 0)
            parent_author = clean_text(top_comment.get("authorDisplayName", ""))

            comments_data.append(
                {
                    "Type": "MAIN COMMENT",
                    "Author": parent_author,
                    "Comment": clean_text(top_comment.get("textDisplay", "")),
                    "Replying_To": "-",
                    "Likes": top_comment.get("likeCount", 0),
                    "Published_At": top_comment.get("publishedAt", ""),
                }
            )

            if total_replies > 0:
                if total_replies <= 5 and "replies" in item:
                    for reply_item in item["replies"]["comments"]:
                        reply = reply_item["snippet"]
                        comments_data.append(
                            {
                                "Type": "REPLY",
                                "Author": clean_text(reply.get("authorDisplayName", "")),
                                "Comment": clean_text(reply.get("textDisplay", "")),
                                "Replying_To": parent_author,
                                "Likes": reply.get("likeCount", 0),
                                "Published_At": reply.get("publishedAt", ""),
                            }
                        )
                else:
                    comments_data.extend(
                        fetch_all_replies(youtube, parent_id, parent_author)
                    )

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return comments_data


def create_workbook(comments_data, title):
    filename = f"{sanitize_filename(title) or 'youtube-comments'}.xlsx"
    workbook_file = BytesIO()
    dataframe = pd.DataFrame(comments_data, columns=COLUMNS)
    dataframe.to_excel(workbook_file, index=False, engine="openpyxl")

    workbook_file.seek(0)
    workbook = openpyxl.load_workbook(workbook_file)
    worksheet = workbook.active

    column_widths = {
        "A": 16,
        "B": 22,
        "C": 75,
        "D": 22,
        "E": 10,
        "F": 22,
    }

    for column, width in column_widths.items():
        worksheet.column_dimensions[column].width = width

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(
        start_color="1F4E79", end_color="1F4E79", fill_type="solid"
    )

    for cell in worksheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(
                wrap_text=True, vertical="top", horizontal="left"
            )

    finalized_workbook = BytesIO()
    workbook.save(finalized_workbook)
    finalized_workbook.seek(0)
    return filename, finalized_workbook


def extract_video(youtube, url_or_id):
    video_id = get_video_id(url_or_id)
    title, thumbnail_url = get_video_metadata(youtube, video_id)
    comments_data = fetch_comments(youtube, video_id)
    filename, workbook = create_workbook(comments_data, title)
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"

    return ExtractionResult(
        video_id=video_id,
        video_url=canonical_url,
        title=title,
        thumbnail_url=thumbnail_url,
        filename=filename,
        workbook=workbook,
    )
