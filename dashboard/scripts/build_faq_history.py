# -*- coding: utf-8 -*-
"""
build_faq_history.py — git 기록에서 'FAQ 항목 수 추이'를 뽑아 JSON으로 저장한다.

faq.md가 바뀐 커밋마다 그 시점의 faq.md를 faq_engine.load_faq()로 읽어
항목 수를 센다. 같은 날 여러 커밋이 있으면 그날의 마지막 값만 남긴다.

도커 이미지 안에는 .git이 없으므로, 배포 전에 로컬에서 한 번 실행해
결과 파일(dashboard/api/app/data/faq_history.json)을 함께 커밋한다.

사용법 (저장소 루트에서):
    python dashboard/scripts/build_faq_history.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "api" / "app" / "data" / "faq_history.json"

sys.path.insert(0, str(ROOT))
from faq_engine import load_faq  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main() -> None:
    log = git("log", "--reverse", "--format=%H %ad", "--date=iso-strict", "--", "faq.md").strip().splitlines()
    by_day: dict = {}
    for line in log:
        commit, when = line.split(" ", 1)
        content = git("show", f"{commit}:faq.md")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        entries = load_faq(tmp)
        Path(tmp).unlink(missing_ok=True)
        by_day[when[:10]] = len(entries)  # 같은 날이면 나중 커밋 값으로 덮어쓴다

    rows = [{"date": d, "entries": n} for d, n in sorted(by_day.items())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FAQ 추이 {len(rows)}일치 저장: {OUT}")


if __name__ == "__main__":
    main()
