#!/usr/bin/env python3

import unittest

from sync_latest import ListingItem, parse_detail, parse_listing, select_items, source_id_from_title


class SyncLatestTests(unittest.TestCase):
    def test_listing_deduplicates_image_and_title_links(self):
        markup = """
        <a href="https://rihp.re.kr/bbs/board.php?bo_table=annual&amp;wr_id=9&amp;page=1"><img></a>
        <a href="https://rihp.re.kr/bbs/board.php?bo_table=annual&amp;wr_id=9&amp;page=1">2022 연례보고서</a>
        """
        items = parse_listing(markup, "annual")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].wr_id, 9)
        self.assertEqual(items[0].title, "2022 연례보고서")

    def test_detail_extracts_title_date_and_pdf(self):
        markup = """
        <h2 id="bo_v_title"><span>[이슈브리핑 16호] 지역의사제</span></h2>
        <strong class="if_date">작성일 26-06-19 10:00</strong>
        <a href="https://rihp.re.kr/bbs/download.php?bo_table=policy_analysis&amp;wr_id=123&amp;no=1"
           class="view_file_download"><strong>issue-16.pdf</strong> (1.0M)</a>
        """
        detail = parse_detail(markup)
        self.assertEqual(detail.title, "[이슈브리핑 16호] 지역의사제")
        self.assertEqual(detail.published_at, "2026-06-19")
        self.assertIn("wr_id=123", detail.pdf_url)

    def test_source_ids(self):
        self.assertEqual(
            source_id_from_title("[연구보고서 2026-02] 환자안전", "research_report", "2026-07-09"),
            "rihp-research-report-2026-02",
        )
        self.assertEqual(
            source_id_from_title("계간의료정책포럼 제23권 3호", "publication_forum", "2025-10-01"),
            "rihp-forum-2025-v23-n3",
        )
        self.assertEqual(
            source_id_from_title("2022 연례보고서", "annual", "2023-04-04"),
            "rihp-annual-report-2022",
        )

    def test_zero_limit_selects_nothing(self):
        item = ListingItem("research_report", 1, "보고서", "https://example.test")
        selected = select_items({"research_report": [item]}, {"research_report": 0}, set())
        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main()
