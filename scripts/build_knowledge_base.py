# -*- coding: utf-8 -*-
"""데이터바우처 산출물(온톨로지 트리플 CSV)로 서비스용 지식베이스 파일을 만든다.

    python scripts/build_knowledge_base.py <트리플 CSV> <출력 .json.gz> [--version 2026-11-26.v1]
    python scripts/build_knowledge_base.py <트리플 CSV> <출력 .json.gz> --upload knowledge-base/ontology_triples_kb_v1.json.gz

- 입력: TB_YFIELD_FACTOR_GCODE_ONTOLOGY_TRIPLES.csv (2,971건, 41컬럼)
- 보고서 식별자(source_report_id)·G-code 원문·시계열 같은 컬럼은 넣지 않는다.
- 만든 파일은 공개 저장소에 올리지 않는다. 서버에는 아래 중 하나로 알려 준다.
    KNOWLEDGE_BASE_PATH=<로컬 파일 경로>
    KNOWLEDGE_BASE_STORAGE=<버킷>/<객체>   (--upload 로 올린 경우, 비공개 버킷)
"""
import argparse
import csv
import datetime
import gzip
import hashlib
import json
import os
import sys

KEEP = [
    "triple_id", "symptom_type", "symptom_severity", "cause_param", "cause_value", "cause_ref_range",
    "solution_text", "solution_label", "grade", "confidence", "c_score", "r_score", "f_score", "d_score",
    "shacl_pass", "data_source", "symptom_desc", "impact", "mechanism", "defect_manifestation", "resolution_basis",
]
FLOATS = ("confidence", "c_score", "r_score", "f_score", "d_score")


def build(src: str, version: str) -> dict:
    csv.field_size_limit(10 ** 9)
    rows = []
    with open(src, encoding="utf-8-sig", newline="") as f:
        for t in csv.DictReader(f):
            o = {k: t.get(k) for k in KEEP}
            for k in FLOATS:
                o[k] = float(o[k]) if o[k] not in ("", None) else None
            o["shacl_pass"] = str(o["shacl_pass"]).lower() == "true"
            rows.append(o)
    with open(src, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    meta = {
        "kb_name": "FACTOR G-code ontology triples (symptom-cause-solution)",
        "kb_version": version,
        "source_file": os.path.basename(src),
        "source_sha256": sha,
        "rows": len(rows),
        "fields": KEEP,
        "excluded": "source_report_id, gcode_line, gcode_context, signal_series 등 식별자·원문·시계열 컬럼 제외",
        "weight": "confidence = W(n)=D(t)x(0.3C+0.5R+0.2F) (경로검증 위반 x0.05, 생성분 보정 포함)",
        "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    return {"meta": meta, "triples": rows}


def upload(path: str, spec: str) -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from supabase_client import get_supabase_client

    bucket, _, obj = spec.strip("/").partition("/")
    client = get_supabase_client()
    names = {b.name for b in client.storage.list_buckets()}
    if bucket not in names:
        client.storage.create_bucket(bucket, options={"public": False})
    with open(path, "rb") as f:
        client.storage.from_(bucket).upload(obj, f.read(), {"content-type": "application/gzip", "upsert": "true"})
    print(f"업로드: {bucket}/{obj} (비공개 버킷)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--version", default=datetime.date.today().isoformat() + ".v1")
    ap.add_argument("--upload", help="Supabase Storage '버킷/객체' 경로에 올린다 (서비스 키 필요)")
    args = ap.parse_args()
    kb = build(args.src, args.version)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False)
    print(f"{kb['meta']['rows']}건 → {args.out} ({os.path.getsize(args.out):,} bytes)")
    if args.upload:
        upload(args.out, args.upload)


if __name__ == "__main__":
    main()
