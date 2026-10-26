from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.revision_audit import csv_bytes, evidence_quality, summarize_journeys


NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def seed(n, statuses=(), events=()):
    vid = f"V{n}"
    cid = f"C{n}"
    journey = {"vehicle_id": vid, "customer_id": cid, "company_name": "Autovema", "status": "ativa"}
    vehicles = {vid: {"plate": f"ABC{n}12", "chassis": f"000000000000000{n}", "model": "Toro"}}
    customers = {cid: {"name": f"Cliente {n}"}}
    revisions = [{"vehicle_id": vid, "revision_number": i, "status": status} for i, status in statuses]
    all_events = [{**e, "vehicle_id": vid} for e in events]
    return summarize_journeys([journey], vehicles, customers, revisions, all_events, now=NOW)


class RevisionAuditTests(unittest.TestCase):
    def test_all_five_confirmed(self):
        data = seed(1, [(i, "realizada") for i in range(1, 6)])
        row = data["rows"][0]
        self.assertEqual(row["completed"], 5)
        self.assertEqual(row["situation_key"], "completo")
        self.assertFalse(row["has_gap"])
        self.assertEqual(data["by_stage"][5]["realizada"], 1)
        self.assertEqual(data["stage_due_cohort"][5], 1)

    def test_later_revision_does_not_prove_missing_stage_evasion(self):
        data = seed(2, [(1, "realizada"), (2, "pendente"), (3, "realizada")])
        row = data["rows"][0]
        self.assertEqual(row["completed"], 2)
        self.assertEqual(row["gap_stages"], [2])
        self.assertEqual(row["stages"][2]["state"], "lacuna")
        self.assertFalse(row["has_external"])

    def test_note_is_indication_not_completed(self):
        data = seed(3, [(1, "pendente")], [{
            "revision_number": 1, "classification": "verificar",
            "confidence": "observacao", "review_override": None,
        }])
        row = data["rows"][0]
        self.assertEqual(row["completed"], 0)
        self.assertEqual(row["stages"][1]["state"], "indicio")

    def test_external_evasion_only_if_explicit(self):
        data = seed(4, [(1, "externa_perdida"), (2, "realizada")])
        row = data["rows"][0]
        self.assertTrue(row["has_external"])
        self.assertEqual(row["situation_key"], "evasao")

    def test_overdue_unconfirmed(self):
        result = summarize_journeys(
            [{"vehicle_id": "V5", "customer_id": "C5"}], {}, {},
            [{"vehicle_id": "V5", "revision_number": 2, "status": "pendente",
              "due_date": datetime(2026, 7, 1, tzinfo=timezone.utc)}],
            [], now=NOW,
        )
        self.assertEqual(result["rows"][0]["stages"][2]["state"], "vencida")

    def test_evidence_quality_distinguishes_unlinked(self):
        quality = evidence_quality([
            {"vehicle_id": None, "classification": "verificar", "link_status": "unmatched_vehicle"},
            {"vehicle_id": "V1", "classification": "verificar", "revision_number": 1, "link_status": "matched"},
            {"vehicle_id": "V1", "classification": "confirmada", "revision_number": 2, "link_status": "matched"},
        ], {"V1"})
        self.assertEqual(quality["totals"]["all_events"], 3)
        self.assertEqual(quality["totals"]["unlinked_vehicle"], 1)
        self.assertEqual(quality["totals"]["linked_selected"], 2)
        self.assertEqual(quality["totals"]["confirmed_events"], 1)

    def test_future_stage_not_in_due_cohort(self):
        data = summarize_journeys(
            [{"vehicle_id": "V8", "customer_id": "C8"}], {}, {},
            [{"vehicle_id": "V8", "revision_number": 5, "status": "pendente",
              "due_date": datetime(2028, 1, 1, tzinfo=timezone.utc)}],
            [], now=NOW,
        )
        self.assertEqual(data["stage_due_cohort"].get(5, 0), 0)
        self.assertEqual(data["by_stage"][5]["pendente"], 1)

    def test_discarded_does_not_become_reviewable(self):
        data = seed(7, [(1, "pendente")], [{
            "revision_number": 1, "classification": "verificar",
            "review_override": "descartada", "confidence": "observacao",
        }])
        self.assertEqual(data["rows"][0]["stages"][1]["state"], "pendente")

    def test_csv_formula_injection_protected(self):
        text = csv_bytes([{"Cliente": "=HYPERLINK(1)", "Placa": "+123"}]).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", text)
        self.assertIn("'+123", text)


if __name__ == "__main__":
    unittest.main()
