"""Regras puras: SIGMEC histórico separado da retenção dos compradores."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.revision_bi import stage_from_code, summarize_customers, summarize_sigmec


CATALOG = {
    "0010A14": "REVISÃO DE ENTREGA",
    "0010C21": "1ª REVISÃO FLEX - KM OU TEMPO",
    "0010F36": "2ª REVISÃO FLEX - KM OU TEMPO",
    "0010F38": "4ª REVISÃO FLEX / 2ª REVISÃO DIESEL - KM OU TEMPO",
    "0010F42": "7ª REVISÃO FLEX - KM OU TEMPO",
}


def row(key, code, order_id=None, status="sem_os_conciliada", dealer="0000001"):
    return {
        "_id": key,
        "os_number": key,
        "dealer_code": dealer,
        "rof080_order_id": order_id,
        "interventions": [{"code": code}],
        "revision_results": [{"code": code, "status": status}],
    }


class RevisionBI(unittest.TestCase):
    def test_delivery_not_periodic(self):
        self.assertIsNone(stage_from_code("0010A14", CATALOG, "STRADA FLEX"))

    def test_mixed_code_requires_fuel(self):
        self.assertIsNone(stage_from_code("0010F38", CATALOG, "STRADA"))
        self.assertEqual(stage_from_code("0010F38", CATALOG, "STRADA FLEX"), 4)
        self.assertEqual(stage_from_code("0010F38", CATALOG, "DUCATO DIESEL"), 2)

    def test_unique_code_can_classify_without_vehicle_but_not_confirm(self):
        stats = summarize_sigmec([row("1", "0010C21")], catalog=CATALOG)
        self.assertEqual(stats["revision_os"], 1)
        self.assertEqual(stats["by_stage"][1], 1)
        self.assertEqual(stats["revision_unlinked"], 1)
        self.assertEqual(stats["confirmed_current"], 0)

    def test_imported_duplicate_order_not_double_counted(self):
        original = row("1", "0010C21")
        stats = summarize_sigmec([original, dict(original)], catalog=CATALOG)
        self.assertEqual(stats["total_os"], 1)
        self.assertEqual(stats["by_stage"][1], 1)

    def test_stage_seven_is_excluded(self):
        stats = summarize_sigmec([row("2", "0010F42")], catalog=CATALOG)
        self.assertEqual(stats["revision_os"], 0)

    def test_delivery_is_excluded(self):
        stats = summarize_sigmec([row("1", "0010A14")], catalog=CATALOG)
        self.assertEqual(stats["total_os"], 1)
        self.assertEqual(stats["revision_os"], 0)

    def test_rof080_link_does_not_imply_confirmed(self):
        stats = summarize_sigmec([row("1", "0010F36", "os-a", "etapa_identificada_pendente")],
                                 {"os-a": {"model": "MOBI FLEX", "chassis": "123"}}, CATALOG)
        self.assertEqual(stats["revision_linked"], 1)
        self.assertEqual(stats["confirmed_current"], 0)
        self.assertEqual(stats["by_status"]["pendente_validacao"], 1)

    def test_confirmed_status_counted_once(self):
        stats = summarize_sigmec([row("1", "0010C21", "os-a", "confirmada")],
                                 {"os-a": {"model": "MOBI FLEX"}}, CATALOG)
        self.assertEqual(stats["confirmed_current"], 1)

    def test_mixed_without_model_remains_ambiguous(self):
        stats = summarize_sigmec([row("1", "0010F38")], catalog=CATALOG)
        self.assertEqual(stats["ambiguous"], 1)
        self.assertEqual(stats["by_stage"], {})

    def test_clients_distinct(self):
        rows = [
            {"customer_id": "a", "customer_name": "Cliente A", "completed": 1,
             "has_gap": False, "has_pending_evidence": False},
            {"customer_id": "a", "customer_name": "Cliente A", "completed": 5,
             "has_gap": False, "has_pending_evidence": True},
            {"customer_id": "b", "customer_name": "Cliente B", "completed": 0,
             "has_gap": True, "has_pending_evidence": False},
        ]
        result = summarize_customers(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["Revisões comprovadas"], 6)
        self.assertEqual(result[0]["Com 5 revisões"], 1)
        self.assertEqual(result[0]["Com alguma revisão"], 2)


if __name__ == "__main__":
    unittest.main()
