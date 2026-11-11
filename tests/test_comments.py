import unittest
import zipfile

import openpyxl

from comments import create_workbook, extract_video, get_video_id


class FakeRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeResource:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(self.response)


class FakeYoutube:
    def __init__(self):
        self.video_resource = FakeResource(
            {
                "items": [
                    {
                        "snippet": {
                            "title": "A: video?",
                            "thumbnails": {
                                "high": {"url": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"}
                            },
                        }
                    }
                ]
            }
        )
        self.thread_resource = FakeResource(
            {
                "items": [
                    {
                        "snippet": {
                            "topLevelComment": {
                                "id": "parent-comment",
                                "snippet": {
                                    "authorDisplayName": "Main author",
                                    "textDisplay": "Main comment",
                                    "likeCount": 4,
                                    "publishedAt": "2026-01-01T00:00:00Z",
                                },
                            },
                            "totalReplyCount": 1,
                        },
                        "replies": {
                            "comments": [
                                {
                                    "snippet": {
                                        "authorDisplayName": "Reply author",
                                        "textDisplay": "Reply text",
                                        "likeCount": 2,
                                        "publishedAt": "2026-01-02T00:00:00Z",
                                    }
                                }
                            ]
                        },
                    }
                ]
            }
        )

    def videos(self):
        return self.video_resource

    def commentThreads(self):
        return self.thread_resource


class VideoUrlTests(unittest.TestCase):
    def test_extracts_supported_youtube_url_forms(self):
        video_id = "abcdefghijk"
        urls = [
            video_id,
            f"https://www.youtube.com/watch?v={video_id}&list=playlist",
            f"https://youtu.be/{video_id}?si=share",
            f"https://m.youtube.com/shorts/{video_id}",
            f"https://youtube.com/embed/{video_id}",
            f"youtube.com/live/{video_id}",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(get_video_id(url), video_id)

    def test_rejects_non_video_or_non_youtube_urls(self):
        for url in (
            "",
            "https://example.com/watch?v=abcdefghijk",
            "ftp://youtube.com/watch?v=abcdefghijk",
            "https://youtu.be/abcdefghijk/extra",
            "not-a-video1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    get_video_id(url)


class WorkbookTests(unittest.TestCase):
    def test_existing_workbook_shape_and_styles_are_preserved(self):
        filename, workbook_file = create_workbook(
            [
                {
                    "Type": "MAIN COMMENT",
                    "Author": "Main author",
                    "Comment": "Main comment",
                    "Replying_To": "-",
                    "Likes": 4,
                    "Published_At": "2026-01-01T00:00:00Z",
                },
                {
                    "Type": "REPLY",
                    "Author": "Reply author",
                    "Comment": "Reply text",
                    "Replying_To": "Main author",
                    "Likes": 2,
                    "Published_At": "2026-01-02T00:00:00Z",
                },
            ],
            "A: video?",
        )

        self.assertEqual(filename, "A video.xlsx")
        workbook = openpyxl.load_workbook(workbook_file)
        worksheet = workbook.active
        self.assertEqual(
            [cell.value for cell in worksheet[1]],
            ["Type", "Author", "Comment", "Replying_To", "Likes", "Published_At"],
        )
        self.assertEqual(
            [worksheet.cell(row=2, column=1).value, worksheet.cell(row=3, column=1).value],
            ["MAIN COMMENT", "REPLY"],
        )
        self.assertEqual(worksheet.column_dimensions["C"].width, 75)
        self.assertEqual(worksheet["A1"].fill.fgColor.rgb, "001F4E79")
        self.assertTrue(worksheet["A1"].font.bold)
        self.assertTrue(worksheet["C2"].alignment.wrap_text)

    def test_empty_workbook_still_has_the_expected_columns(self):
        _, workbook_file = create_workbook([], "Video")
        workbook = openpyxl.load_workbook(workbook_file)
        self.assertEqual(
            [cell.value for cell in workbook.active[1]],
            ["Type", "Author", "Comment", "Replying_To", "Likes", "Published_At"],
        )

    def test_workbook_is_a_single_zip_archive_starting_at_byte_zero(self):
        _, workbook_file = create_workbook([], "Video")
        workbook_file.seek(0)
        with zipfile.ZipFile(workbook_file) as archive:
            self.assertEqual(
                min(info.header_offset for info in archive.infolist()),
                0,
            )

    def test_extraction_uses_submitted_video_and_keeps_reply_order(self):
        youtube = FakeYoutube()
        result = extract_video(youtube, "https://youtu.be/abcdefghijk")

        self.assertEqual(result.video_id, "abcdefghijk")
        self.assertEqual(result.video_url, "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(
            result.thumbnail_url,
            "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
        )
        self.assertEqual(result.filename, "A video.xlsx")
        self.assertEqual(youtube.video_resource.calls[0]["id"], "abcdefghijk")
        self.assertEqual(youtube.thread_resource.calls[0]["order"], "time")

        workbook = openpyxl.load_workbook(result.workbook)
        worksheet = workbook.active
        self.assertEqual(worksheet["A2"].value, "MAIN COMMENT")
        self.assertEqual(worksheet["C2"].value, "Main comment")
        self.assertEqual(worksheet["A3"].value, "REPLY")
        self.assertEqual(worksheet["C3"].value, "Reply text")


if __name__ == "__main__":
    unittest.main()
