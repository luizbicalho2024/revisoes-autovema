from __future__ import annotations

import unittest
from datetime import datetime, timezone
from src.revision_audit import summarize_journeys, verified_service_event
from src.debug_export import anonymize, COLLECTIONS

NOW=datetime(2026,10,26,tzinfo=timezone.utc)
JOURNEY={"vehicle_id":"V1","customer_id":"C1","status":"ativa"}
VEHICLES={"V1":{"plate":"NAX3E00","chassis":"9BW12345678900001","model":"Toro"}}
CUSTOMERS={"C1":{"name":"Pessoa Teste"}}
BASE={"vehicle_id":"V1","revision_number":1,"classification":"confirmada","confidence":"servico",
      "evidence_source":"servico","closed_at":NOW,"post_sale":True,"owner_match":True,
      "link_status":"matched","service_date":NOW,"os_number":"123","service_order_id":"os:1"}

class ImportedRevisionTests(unittest.TestCase):
    def test_service_from_rof080_counts_as_completed_without_journey_record(self):
        data=summarize_journeys([JOURNEY],VEHICLES,CUSTOMERS,[],[BASE],NOW)
        row=data["rows"][0]
        self.assertEqual(row["completed"],1)
        self.assertEqual(row["stages"][1]["state"],"realizada")
        self.assertEqual(row["completed_from_rof080"],1)
        self.assertEqual(row["stages"][1]["source"],"rof080_confirmado")

    def test_observation_not_realized(self):
        event={**BASE,"confidence":"observacao","evidence_source":"observacao"}
        self.assertFalse(verified_service_event(event))
        self.assertEqual(summarize_journeys([JOURNEY],VEHICLES,CUSTOMERS,[],[event],NOW)["rows"][0]["completed"],0)

    def test_closed_and_post_sale_required(self):
        for props in ({"closed_at":None},{"post_sale":False},{"link_status":"unmatched_vehicle"},
                      {"owner_match":False},{"review_override":"descartada"},{"revision_number":7}):
            with self.subTest(props=props):
                self.assertFalse(verified_service_event({**BASE,**props}))

    def test_manual_review_eligible(self):
        event={**BASE,"classification":"verificar","confidence":"observacao",
               "review_override":"confirmada","manual_revision_number":2}
        self.assertTrue(verified_service_event(event))
        row=summarize_journeys([JOURNEY],VEHICLES,CUSTOMERS,[],[event],NOW)["rows"][0]
        self.assertEqual(row["stages"][2]["state"],"realizada")

    def test_anonymized_export_keeps_relationships_but_not_pii(self):
        salt=b'test-only-salt-unique'
        original={"customer_id":"CPF-123","vehicle_id":"chassi-ABC","name":"Maria",
                  "document":"00011122233","plate":"ABC1D23","evidence_text":"Revisao dona Maria",
                  "password_hash":"secret","revision_number":2,"status":"realizada"}
        result=anonymize(original,salt)
        self.assertEqual(result["customer_id"],anonymize("CPF-123",salt,"customer_id"))
        self.assertNotIn("Maria",repr(result))
        self.assertNotIn("00011122233",repr(result))
        self.assertNotIn("secret",repr(result))
        self.assertEqual(result["revision_number"],2)
        self.assertEqual(result["status"],"realizada")
        self.assertNotEqual(anonymize({"phone": 69999999999}, salt)["phone"], 69999999999)
        self.assertIn("revision_events",COLLECTIONS)

if __name__=="__main__": unittest.main()
