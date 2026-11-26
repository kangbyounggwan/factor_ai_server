"""온톨로지 트리플 지식베이스 시험 (합성 데이터 — 실제 데이터 없이 동작)

실행 (저장소 루트에서):
    python -m unittest tests.test_knowledge_base -v
"""
import asyncio
import gzip
import json
import os
import tempfile
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gcode_analyzer.knowledge import (
    KnowledgeBase,
    get_knowledge_base,
    set_knowledge_base,
    similar_cases_for_issue,
    tokenize,
)
from gcode_analyzer.knowledge.router import router as knowledge_router

TRIPLES = [
    {"triple_id": "T1", "symptom_type": "cold_extrusion", "cause_param": "temp_nozzle", "cause_value": "150",
     "cause_ref_range": "180~220°C", "solution_text": "M104 S200 후 M109 S200 대기 추가",
     "solution_label": "add_temp_wait", "confidence": 0.9, "data_source": "field_llm",
     "symptom_desc": "노즐 온도가 너무 낮아 압출 불량"},
    {"triple_id": "T2", "symptom_type": "cold_extrusion", "cause_param": "temp_nozzle", "cause_value": "120",
     "solution_text": "M104 S200 후 M109 S200 대기 추가", "solution_label": "add_temp_wait",
     "confidence": 0.3, "data_source": "synthetic_sweep"},
    {"triple_id": "T3", "symptom_type": "excessive_speed", "cause_param": "feed_rate", "cause_value": "400",
     "solution_text": "이송 속도를 300mm/s 이하로 낮춤", "solution_label": "reduce_speed",
     "confidence": 0.8, "data_source": "field_llm"},
    {"triple_id": "T4", "symptom_type": "high_retraction", "cause_param": "retraction_length", "cause_value": "12",
     "solution_text": "리트랙션 거리를 줄임", "solution_label": "reduce_retraction",
     "confidence": 0.5, "data_source": "field_rule"},
    {"triple_id": "T5", "symptom_type": "no_bed_temp", "cause_param": "temp_bed", "cause_value": "0",
     "solution_text": "M140 S60 베드 온도 설정 추가", "solution_label": "add_bed_temp",
     "confidence": 0.7, "data_source": "field_llm"},
]
META = {"kb_version": "test.v1", "source_file": "synthetic"}


def make_kb():
    return KnowledgeBase([dict(t) for t in TRIPLES], dict(META))


class TokenizeTest(unittest.TestCase):
    def test_english_words_and_korean_bigrams(self):
        self.assertEqual(tokenize("Cold_Extrusion 노즐온도"), ["cold_extrusion", "노즐", "즐온", "온도"])

    def test_single_korean_character_kept(self):
        self.assertEqual(tokenize("열 M104"), ["m104", "열"])


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.kb = make_kb()

    def test_finds_relevant_symptom(self):
        top = self.kb.search("저온 압출 cold_extrusion temp_nozzle", top_k=3)
        self.assertEqual(top[0]["symptom_type"], "cold_extrusion")

    def test_weight_reranks_equal_text_candidates(self):
        # T1·T2 는 검색 문구가 같고 신뢰도만 다르다 → 신뢰도 높은 T1 이 먼저
        top = self.kb.search("cold_extrusion temp_nozzle M109 대기", top_k=2)
        self.assertEqual([r["triple_id"] for r in top], ["T1", "T2"])
        self.assertGreater(top[0]["score"], top[1]["score"])

    def test_symptom_filter(self):
        top = self.kb.search("속도 온도 리트랙션", top_k=5, symptom_type="excessive_speed")
        self.assertTrue(top)
        self.assertTrue(all(r["symptom_type"] == "excessive_speed" for r in top))

    def test_unknown_symptom_filter_returns_empty(self):
        self.assertEqual(self.kb.search("아무 질의", symptom_type="not_a_symptom"), [])

    def test_no_lexical_overlap_within_symptom_falls_back_to_weight(self):
        top = self.kb.search("zzz", top_k=2, symptom_type="cold_extrusion")
        self.assertEqual([r["triple_id"] for r in top], ["T1", "T2"])

    def test_similar_for_known_issue_type(self):
        top = self.kb.similar_for_issue("no_bed_temp", "베드 온도 없음", top_k=3)
        self.assertEqual(top[0]["triple_id"], "T5")

    def test_similar_for_unknown_issue_type_uses_text(self):
        top = self.kb.similar_for_issue("bed_adhesion_fail", "베드 온도 설정이 빠짐", top_k=3)
        self.assertEqual(top[0]["triple_id"], "T5")

    def test_results_carry_scores_but_no_identifiers(self):
        r = self.kb.search("리트랙션", top_k=1)[0]
        for key in ("score", "bm25", "weight_normalized", "confidence", "solution_text"):
            self.assertIn(key, r)
        for key in ("source_report_id", "gcode_context", "signal_series", "pseudo_user_id"):
            self.assertNotIn(key, r)

    def test_stats(self):
        s = self.kb.stats()
        self.assertEqual(s["count"], 5)
        self.assertEqual(s["symptom_types"], 4)
        self.assertEqual(s["version"], "test.v1")

    def test_from_bytes_plain_and_gzip(self):
        raw = json.dumps({"meta": META, "triples": TRIPLES}, ensure_ascii=False).encode("utf-8")
        self.assertEqual(len(KnowledgeBase.from_bytes(raw)), 5)
        self.assertEqual(len(KnowledgeBase.from_bytes(gzip.compress(raw))), 5)

    def test_empty_kb_is_rejected(self):
        with self.assertRaises(ValueError):
            KnowledgeBase([])


class ServiceInstanceTest(unittest.TestCase):
    def tearDown(self):
        for k in ("KNOWLEDGE_BASE_PATH", "KNOWLEDGE_BASE_STORAGE"):
            os.environ.pop(k, None)
        set_knowledge_base(None)

    def test_loads_from_env_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "kb.json.gz")
            with gzip.open(p, "wt", encoding="utf-8") as f:
                json.dump({"meta": META, "triples": TRIPLES}, f, ensure_ascii=False)
            os.environ["KNOWLEDGE_BASE_PATH"] = p
            kb = get_knowledge_base(reload=True)
            self.assertIsNotNone(kb)
            self.assertEqual(len(kb), 5)

    def test_missing_file_gives_none_not_error(self):
        os.environ["KNOWLEDGE_BASE_PATH"] = os.path.join(tempfile.gettempdir(), "no_such_kb_file.json.gz")
        self.assertIsNone(get_knowledge_base(reload=True))

    def test_not_configured_gives_none(self):
        self.assertIsNone(get_knowledge_base(reload=True))

    def test_similar_cases_for_issue(self):
        set_knowledge_base(None)
        self.assertEqual(similar_cases_for_issue({"type": "cold_extrusion"}), [])
        set_knowledge_base(make_kb())
        cases = similar_cases_for_issue({"type": "cold_extrusion", "title": "저온 압출", "description": "노즐 온도 낮음"})
        self.assertEqual(cases[0]["symptom_type"], "cold_extrusion")


class IssueResolverIntegrationTest(unittest.TestCase):
    """이슈 해결 결과에 knowledge_cases 가 붙는지 (LLM 호출은 실패하게 바꿔 대체 응답 경로로 확인)"""

    def tearDown(self):
        set_knowledge_base(None)

    def test_resolution_carries_knowledge_cases(self):
        from gcode_analyzer.llm import issue_resolver

        class FailingLLM:
            async def ainvoke(self, *args, **kwargs):
                raise RuntimeError("LLM 호출 없음 (시험)")

        set_knowledge_base(make_kb())
        issue = {"id": "ISSUE-001", "line": 10, "type": "cold_extrusion", "severity": "high",
                 "title": "저온 압출", "description": "노즐 온도가 너무 낮음", "gcode_context": "M104 S150"}
        with mock.patch.object(issue_resolver, "get_llm_client", return_value=FailingLLM()):
            result = asyncio.run(issue_resolver.resolve_issue(issue))
        self.assertIn("resolution", result)
        self.assertEqual(result["knowledge_cases"][0]["symptom_type"], "cold_extrusion")


class ApiTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(knowledge_router)
        self.client = TestClient(app)

    def tearDown(self):
        set_knowledge_base(None)

    def test_stats_without_kb(self):
        set_knowledge_base(None)
        self.assertEqual(self.client.get("/api/v1/knowledge/stats").json(), {"available": False})

    def test_search_without_kb_is_503(self):
        set_knowledge_base(None)
        r = self.client.post("/api/v1/knowledge/search", json={"query": "노즐 온도"})
        self.assertEqual(r.status_code, 503)

    def test_endpoints_with_kb(self):
        set_knowledge_base(make_kb())
        s = self.client.get("/api/v1/knowledge/stats").json()
        self.assertTrue(s["available"])
        self.assertEqual(s["count"], 5)
        r = self.client.post("/api/v1/knowledge/search", json={"query": "베드 온도", "top_k": 2}).json()
        self.assertEqual(r["results"][0]["triple_id"], "T5")
        r = self.client.get("/api/v1/knowledge/issues/high_retraction", params={"top_k": 1}).json()
        self.assertTrue(r["known_symptom"])
        self.assertEqual(r["results"][0]["triple_id"], "T4")


if __name__ == "__main__":
    unittest.main()
