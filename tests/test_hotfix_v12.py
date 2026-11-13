"""Regressões: importação das cinco telas, catálogo e sincronização SIGMEC."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from pymongo import UpdateOne

from src.catalog_admin import catalog_rows, disable_code, save_code
from src.revision_loader import load_five
from src.revision_taxonomy import catalog_from_database
from src.sigmec_resync import classify_interventions, sync_existing_orders


class Cursor(list):
    def sort(self, *_args):
        return self


class Collection:
    def __init__(self, items=None):
        self.items = {item["_id"]: dict(item) for item in (items or [])}

    def find(self, query=None, projection=None):
        query = query or {}
        rows = []
        for row in self.items.values():
            if self._matches(row, query):
                if projection:
                    row = {key: value for key, value in row.items()
                           if key in projection or key == "_id"}
                rows.append(dict(row))
        return Cursor(rows)

    def find_one(self, query, projection=None):
        return next(iter(self.find(query, projection)), None)

    def count_documents(self, query):
        return len(self.find(query))

    def bulk_write(self, operations, ordered=False):
        for op in operations:
            if hasattr(op, "_filter"):
                self.update_one(op._filter, op._doc, getattr(op, "_upsert", False))
            else:
                self.update_one(op.filter, op.update)

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        if key not in self.items:
            if not upsert:
                return
            self.items[key] = {"_id": key}
        self.items[key].update(update.get("$set", {}))

    @staticmethod
    def _matches(row, query):
        for key, required in query.items():
            current = row.get(key)
            if isinstance(required, dict):
                if "$in" in required and current not in required["$in"]:
                    return False
                if "$ne" in required and current == required["$ne"]:
                    return False
            elif current != required:
                return False
        return True


class DB:
    def __init__(self):
        self.revision_catalog = Collection()
        self.audit_logs = Collection()
        self.journeys = Collection()
        self.vehicles = Collection()
        self.customers = Collection()
        self.revisions = Collection()
        self.revision_events = Collection()
        self.sigmec_orders = Collection()


ADMIN = {"role": "superadmin", "email": "admin@example.test"}


class HotfixV12Tests(unittest.TestCase):
    def test_loader_uses_existing_revision_audit_contract(self):
        db = DB()
        db.journeys = Collection([{"_id": "j1", "vehicle_id": "v1",
                                   "customer_id": "c1", "company_code": 8,
                                   "status": "ativa"}])
        db.vehicles = Collection([{"_id": "v1", "plate": "ABC1234", "model": "Argo"}])
        db.customers = Collection([{"_id": "c1", "name": "Cliente Exemplo"}])
        db.revisions = Collection([{"_id": f"r{n}", "vehicle_id": "v1",
                                    "revision_number": n, "status": "realizada"}
                                   for n in range(1, 6)])
        data = load_five(db, ADMIN)
        self.assertEqual(data["rows"][0]["completed"], 5)
        self.assertIn("by_stage", data)
        self.assertEqual(data["rows"][0]["customer_name"], "Cliente Exemplo")
        self.assertEqual(len(load_five(db, {"role": "operador", "company_codes": []})["rows"]), 1)
        self.assertEqual(load_five(db, {"role": "operador", "company_codes": [99]})["rows"], [])
        self.assertEqual(len(load_five(db, {"role": "operador", "company_codes": [8]})["rows"]), 1)

    def test_default_code_can_be_disabled_and_reactivated(self):
        db = DB()
        self.assertIn("0010C21", catalog_from_database(db))
        with patch("src.catalog_admin.audit"):
            disable_code(db, ADMIN, "0010C21")
            self.assertNotIn("0010C21", catalog_from_database(db))
            self.assertFalse(next(x for x in catalog_rows(db) if x["code"] == "0010C21")["active"])
            save_code(db, ADMIN, "0010C21", "1ª REVISÃO FLEX - KM OU TEMPO")
        self.assertIn("0010C21", catalog_from_database(db))

    def test_invalid_code_and_vague_description_rejected(self):
        db = DB()
        with patch("src.catalog_admin.audit"):
            with self.assertRaises(ValueError):
                save_code(db, ADMIN, "0010A14", "1ª REVISÃO FLEX")
            with self.assertRaises(ValueError):
                save_code(db, ADMIN, "BAD CODE", "2ª REVISÃO FLEX")
            with self.assertRaises(ValueError):
                save_code(db, ADMIN, "0010XYZ", "SERVIÇO GENÉRICO")

    def test_mixed_fuel_must_have_model_and_no_conflicting_stages(self):
        catalog = {"0010F38": "4ª REVISÃO FLEX / 2ª REVISÃO DIESEL",
                   "0010C21": "1ª REVISÃO FLEX"}
        rows, chosen = classify_interventions([{"code": "0010F38"}], catalog, "ARGO")
        self.assertIsNone(chosen)
        rows, chosen = classify_interventions([{"code": "0010F38"}], catalog, "STRADA FLEX")
        self.assertEqual(chosen["code"], "0010F38")
        rows, chosen = classify_interventions([{"code": "0010F38"}, {"code": "0010C21"}],
                                               catalog, "STRADA FLEX")
        self.assertIsNone(chosen)

    def test_sync_invalidates_only_automatic_evidence(self):
        db = DB()
        db.sigmec_orders = Collection([{"_id": "sigmec:1:7", "dealer_code": "0000001",
                                        "os_number": "7", "os_normalized": "7",
                                        "rof080_order_id": "rof:7",
                                        "interventions": [{"code": "0010C21"}]}])
        db.revision_events = Collection([{"_id": "revision:ROF080:rof:7", "sigmec_code": "0010C21",
                                          "revision_number": 1, "classification": "confirmada"}])
        with patch("src.sigmec_resync._find_rof080", return_value={}), \
             patch("src.sigmec_resync.audit"):
            with patch("src.catalog_admin.audit"):
                disable_code(db, ADMIN, "0010C21")
            summary = sync_existing_orders(db, ADMIN)
        self.assertEqual(summary["eventos_anteriores_pendentes"], 1)
        event = db.revision_events.items["revision:ROF080:rof:7"]
        self.assertIsNone(event["revision_number"])
        self.assertEqual(event["classification"], "verificar")

    def test_new_custom_code_is_recognized_in_stored_os(self):
        db = DB()
        db.sigmec_orders = Collection([{"_id": "sigmec:1:7", "dealer_code": "0000001",
                                        "os_number": "7", "os_normalized": "7",
                                        "rof080_order_id": None,
                                        "interventions": [{"code": "0010XYZ"}]}])
        order = {"_id": "rof:7", "model": "ARGO FLEX", "company_dealer": "0000001"}
        with patch("src.catalog_admin.audit"):
            save_code(db, ADMIN, "0010XYZ", "1ª REVISÃO FLEX - KM OU TEMPO")
        with patch("src.sigmec_resync._find_rof080", return_value={"7": [order]}), \
             patch("src.sigmec_resync._pick_order", return_value=(order, "os_localizada")), \
             patch("src.sigmec_resync._audit_evidence", return_value=(
                 UpdateOne({"_id": "revision:ROF080:rof:7"}, {"$set": {"revision_number": 1}}, upsert=True),
                 "confirmada")) as evidence, \
             patch("src.sigmec_resync.audit"):
            result = sync_existing_orders(db, ADMIN)
        self.assertEqual(result["os_vinculadas"], 1)
        self.assertEqual(result["eventos_novos"], 1)
        self.assertEqual(db.sigmec_orders.items["sigmec:1:7"]["revision_results"][0]["code"], "0010XYZ")
        evidence.assert_called_once()

    def test_sync_preserves_manually_confirmed_evidence(self):
        db = DB()
        db.sigmec_orders = Collection([{"_id": "sigmec:1:7", "dealer_code": "0000001",
                                        "os_number": "7", "os_normalized": "7",
                                        "rof080_order_id": "rof:7", "interventions": []}])
        db.revision_events = Collection([{"_id": "revision:ROF080:rof:7", "sigmec_code": "0010C21",
                                          "revision_number": 1, "review_override": "confirmada",
                                          "classification": "confirmada"}])
        with patch("src.sigmec_resync._find_rof080", return_value={}), \
             patch("src.sigmec_resync.audit"):
            sync_existing_orders(db, ADMIN)
        self.assertEqual(db.revision_events.items["revision:ROF080:rof:7"]["revision_number"], 1)


if __name__ == "__main__":
    unittest.main()
