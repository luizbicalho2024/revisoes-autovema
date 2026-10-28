from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sigmec_awards import analyze_awards

CATALOG = {
    "0010A14": "REVISÃO DE ENTREGA",
    "0010C21": "1ª REVISÃO FLEX",
    "0010F36": "2ª REVISÃO FLEX",
    "0010F37": "3ª REVISÃO FLEX",
    "0010F38": "4ª REVISÃO FLEX / 2ª REVISÃO DIESEL",
    "0010F39": "5ª REVISÃO FLEX",
}
CODES = ["0010C21", "0010F36", "0010F37", "0010F38", "0010F39"]


def fake(n, date_offset=None, chassi="9BD12345678912345", owner="12345678901", name="Cliente A", model="STRADA FLEX", code=None):
    code = code or CODES[n-1]
    key = f"service:{chassi}:{owner}:{n}:{date_offset}"
    row = {"_id": f"sigmec:{key}", "os_number": f"{n:08d}", "dealer_code": "0000001", "rof080_order_id": key,
           "interventions": [{"code": code}]}
    service = {"_id": key, "source": "rof080", "chassis": chassi, "owner_document": owner,
               "owner_name": name, "plate": "NAA1234", "model": model,
               "closed_at": datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=60*(date_offset if date_offset is not None else n))}
    return row, service


def run(rows_and_services):
    return analyze_awards([x for x, _ in rows_and_services], {s['_id']:s for _,s in rows_and_services}, CATALOG)


class SigmecAwardTests(unittest.TestCase):
    def test_all_five_same_owner(self):
        result=run([fake(n) for n in range(1,6)])
        self.assertEqual(result['bands'].get('1ª à 5ª'),1)
        self.assertEqual(result['records'][0]['premiacao_candidata'],True)

    def test_only_one(self):
        result=run([fake(1)])
        self.assertEqual(result['bands'].get('Somente 1ª'),1)

    def test_first_second(self):
        result=run([fake(1),fake(2)])
        self.assertEqual(result['bands'].get('1ª à 2ª'),1)

    def test_first_third_not_regular(self):
        result=run([fake(1),fake(3)])
        self.assertEqual(result['bands'].get('Fora da sequência'),1)
        self.assertEqual(result['bands'].get('Somente 1ª',0),0)

    def test_second_only_not_award(self):
        result=run([fake(2)])
        self.assertEqual(result['bands'].get('Fora da sequência'),1)

    def test_same_chassi_different_owners_not_merged(self):
        result=run([fake(1),fake(2,owner="98765432100",name="Cliente B")])
        self.assertEqual(len(result['records']),2)
        self.assertEqual(result['bands'].get('1ª à 2ª',0),0)

    def test_missing_owner_unverified(self):
        result=run([fake(1,owner="")])
        self.assertEqual(result['bands'].get('Proprietário a validar'),1)
        self.assertFalse(result['records'][0]['premiacao_candidata'])

    def test_unlinked_order_is_pending(self):
        row,_=fake(1)
        result=analyze_awards([row],{},CATALOG)
        self.assertEqual(len(result['records']),0)
        self.assertEqual(len(result['issues']),1)

    def test_os_without_closed_date_is_pending(self):
        row,service=fake(1)
        service['closed_at']=None
        result=run([(row,service)])
        self.assertEqual(len(result['records']),0)
        self.assertEqual(len(result['issues']),1)

    def test_delivery_does_not_qualify(self):
        result=run([fake(1,code="0010A14")])
        self.assertEqual(len(result['records']),0)

    def test_ambiguous_without_model_stays_pending(self):
        result=run([fake(4,model="MOTOR DESCONHECIDO")])
        self.assertEqual(len(result['records']),0)
        self.assertEqual(len(result['issues']),1)

    def test_duplicate_order_not_double_counted(self):
        row,service=fake(1)
        result=analyze_awards([row,row],{service['_id']:service},CATALOG)
        self.assertEqual(result['bands'].get('Somente 1ª'),1)

    def test_reverse_date_not_a_sequence(self):
        result=run([fake(1,date_offset=4),fake(2,date_offset=2)])
        self.assertEqual(result['bands'].get('1ª à 2ª',0),0)

    def test_four_stages(self):
        result=run([fake(n) for n in range(1,5)])
        self.assertEqual(result['bands'].get('1ª à 4ª'),1)

    def test_three_stages(self):
        result=run([fake(n) for n in range(1,4)])
        self.assertEqual(result['bands'].get('1ª à 3ª'),1)

if __name__ == '__main__':
    unittest.main()
