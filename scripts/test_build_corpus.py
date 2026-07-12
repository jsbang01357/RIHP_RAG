#!/usr/bin/env python3

import unittest
from pathlib import Path

from build_corpus import (
    DocumentMeta,
    chunk_text,
    clean_catalog_title,
    clean_page_text,
    clean_tripled_glyphs,
    extract_title_page_authors,
    forum_units,
    infer_meta,
    make_units,
    parse_forum_toc,
    report_units,
)


class CorpusTests(unittest.TestCase):
    def test_catalog_title_removes_publication_prefix(self):
        self.assertEqual(
            clean_catalog_title("[연구보고서 2026-02] 의원급 의료기관 환자안전"),
            "의원급 의료기관 환자안전",
        )
        self.assertEqual(
            clean_catalog_title("[이슈브리핑 16호] 지역의사제"),
            "지역의사제",
        )

    def test_page_cleanup_removes_pdf_control_characters(self):
        self.assertEqual(clean_page_text("연례\x00보고서\x07 본문"), "연례보고서 본문")

    def test_tripled_title_cleanup(self):
        self.assertEqual(clean_tripled_glyphs("거거거점점점의의의료료료"), "거점의료")

    def test_policy_metadata(self):
        meta = infer_meta(
            Path("sample.pdf"),
            [
                "정책현안분석 2025-06\n거거거점점점의의의료료료기기기관관관 지정 제도 개선 방안 연구\n"
                "연 구 자 : 강 주 현 (의료정책연구원 연구원)\n신 요 한 (의료정책연구원 연구원)"
            ],
        )
        self.assertEqual(meta.source_id, "rihp-policy-analysis-2025-06")
        self.assertEqual(meta.title, "거점의료기관 지정 제도 개선 방안 연구")
        self.assertEqual(meta.authors, ["강주현", "신요한"])

    def test_title_page_coauthors(self):
        text = "제목\n홍 석 주\n대한의사협회\n최 지 영\n대한의사협회\n1. 서론"
        self.assertEqual(extract_title_page_authors(text), ["홍석주", "최지영"])

    def test_forum_toc(self):
        toc = """CONTENTS
의료정책포럼 Vol.24 No.1
3 시론
특진비 폐지와 온타리오주의 의사 파업 / 안 덕 선
54 해외의료정책 동향
- 일본, 진료 수가 개정안 공개
"""
        items = parse_forum_toc(toc)
        self.assertEqual(items[0][0], "특진비 폐지와 온타리오주의 의사 파업")
        self.assertEqual(items[0][2], ["안덕선"])
        self.assertEqual(items[1][0], "일본, 진료 수가 개정안 공개")

    def test_forum_divider_is_not_article_start(self):
        meta = DocumentMeta("forum", "포럼", "medical-policy-forum", "v1-n1", "2026")
        pages = [
            "CONTENTS\n3 특집\n첫 번째 의료정책 연구방안 분석 / 김 하나\n두 번째 지역의료 개선방안 연구 / 이 둘",
            "특집\n첫 번째 의료정책 연구방안 분석\n두 번째 지역의료 개선방안 연구",
            "첫 번째 의료정책 연구방안 분석\n김 하나\n본문",
            "다음 섹션\n첫 번째 의료정책 연구방안 분석\n두 번째 지역의료 개선방안 연구",
            "두 번째 지역의료 개선방안 연구\n이 둘\n본문",
        ]
        units = forum_units(meta, pages)
        self.assertEqual([unit.start_page for unit in units], [3, 5])
        self.assertEqual(units[0].end_page, 3)

    def test_spaced_research_report_number(self):
        meta = infer_meta(
            Path("sample.pdf"),
            ["연 구 보 고 서\n2 0 2 5 - 1 0\n일본의 의사 수 결정 정책과정 분석"],
        )
        self.assertEqual(meta.source_id, "rihp-research-report-2025-10")

    def test_issue_briefing_metadata(self):
        meta = infer_meta(
            Path("rihp-issue-briefing-15-cms-hcc.pdf"),
            [
                "미국의 계층적 질환군(CMS-HCC) 위험조정 모델 도입의 문제점 분석\n"
                "의료정책연구원\n임선미 책임연구원, 김계현 연구위원"
            ],
        )
        self.assertEqual(meta.source_id, "rihp-issue-briefing-15")
        self.assertEqual(meta.authors, ["임선미", "김계현"])
        units = make_units(meta, ["1쪽", "2쪽", "3쪽"])
        self.assertEqual(len(units), 1)
        self.assertEqual((units[0].start_page, units[0].end_page), (1, 3))

    def test_issue_briefing_number_from_pdf_text(self):
        meta = infer_meta(
            Path("policy-analysis-123.pdf"),
            ["이슈브리핑 제16호\n지역의사 양성 정책 분석\n의료정책연구원"],
        )
        self.assertEqual(meta.source_id, "rihp-issue-briefing-16")

    def test_annual_report_metadata_from_stable_filename(self):
        meta = infer_meta(Path("rihp-annual-report-2022.pdf"), ["ANNUAL REPORT"])
        self.assertEqual(meta.source_id, "rihp-annual-report-2022")
        self.assertEqual(meta.collection, "annual-report")

    def test_research_chapter_uses_toc_title_once(self):
        meta = DocumentMeta("report", "보고서", "research-report", "2025-10", "2025")
        pages = [""] * 25
        pages[0] = "목 차\n제1장❙긴 장 제목 전체······1\n제2장❙두 번째 장 제목······9"
        pages[20] = "제1장 짧은 제목\n본문"
        pages[21] = "제1장 짧은 제목\n계속"
        pages[23] = "제2장 두 번째 장 제목\n본문"
        units = report_units(meta, pages)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0].title, "제1장. 긴 장 제목 전체")
        self.assertEqual(units[0].start_page, 21)

    def test_chunking_overlap(self):
        chunks = chunk_text("가" * 4000, limit=1000, overlap=100)
        self.assertGreaterEqual(len(chunks), 4)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
