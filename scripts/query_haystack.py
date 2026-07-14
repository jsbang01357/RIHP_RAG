#!/usr/bin/env python3
"""로컬 ADC로 RIHP Haystack 하이브리드 검색을 점검한다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from service.rag_service import HybridRagService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()
    service = HybridRagService(generation_enabled=False)
    print(json.dumps(service.answer(args.query, args.top_k), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
