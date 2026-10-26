from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.workshop_history import summarize_workshop, is_service_candidate


def event(chassis='CHASSIS-A', stage=1, link='matched', year='2026', confidence='servico', **extra):
    obj = {
        'chassis':chassis,'revision_number':stage,'closed_at':f'{year}-10-01',
        'service_date':f'{year}-10-01','service_order_id':f'order:{chassis}:{stage}:{year}',
        'confidence':confidence,'evidence_source':'servico','link_status':link,
        'classification':'confirmada' if link=='matched' else 'verificar',
        'post_sale':link=='matched','owner_match':link=='matched','vehicle_id':'vehicle-A' if link!='unmatched_vehicle' else None,
    }
    obj.update(extra)
    return obj


class WorkshopHistoryV8Tests(unittest.TestCase):
    def test_service_stage_confirmed_after_sale(self):
        s=summarize_workshop([event()], ['CHASSIS-A'])
        self.assertEqual(s['confirmed_current'],1)
        self.assertEqual(s['chassis_overlap'],1)
        self.assertEqual(s['candidate_os'],1)

    def test_historic_vehicle_does_not_belong_to_current_buyer(self):
        s=summarize_workshop([event(link='pre_sale',year='2021',post_sale=False,owner_match=False)], ['CHASSIS-A'])
        self.assertEqual(s['confirmed_current'],0)
        self.assertEqual(s['candidate_pre_sale'],1)
        self.assertEqual(s['candidate_in_current_fleet'],1)

    def test_unmatched_workshop_car_not_missing_revision(self):
        s=summarize_workshop([event(chassis='HISTORIC',link='unmatched_vehicle',year='2022')],['CHASSIS-A'])
        self.assertEqual(s['candidate_outside_current_fleet'],1)
        self.assertEqual(s['candidate_chassis'],1)
        self.assertEqual(s['confirmed_current'],0)

    def test_observation_only_never_counts_as_service(self):
        e=event(confidence='observacao',evidence_source='observacao')
        self.assertFalse(is_service_candidate(e))
        s=summarize_workshop([e],['CHASSIS-A'])
        self.assertEqual(s['candidate_os'],0)
        self.assertEqual(s['observation_only'],1)

    def test_duplicate_os_does_not_double_count(self):
        e=event()
        s=summarize_workshop([e,dict(e)],['CHASSIS-A'])
        self.assertEqual(s['candidate_os'],1)
        self.assertEqual(s['duplicates'],1)

    def test_ambiguous_stage_never_promoted(self):
        e=event(stage=None,confidence='ambiguo')
        s=summarize_workshop([e],['CHASSIS-A'])
        self.assertEqual(s['candidate_os'],0)
        self.assertEqual(s['ambiguous'],1)

    def test_discarded_manual_is_not_candidate(self):
        e=event(review_override='descartada')
        s=summarize_workshop([e],['CHASSIS-A'])
        self.assertEqual(s['candidate_os'],0)
        self.assertEqual(s['confirmed_current'],0)

    def test_debug_export_redacts_raw_source_and_dealer_identifier(self):
        from src.debug_export import safe_document
        s=safe_document("revision_events", {
            "_id":"event-1", "company_dealer":"03968287000136",
            "source_raw":{"NotaFiscal_PessoaCod":122045},
            "revision_number":1,
        }, b"unique-salt-123")
        self.assertNotIn("source_raw", s)
        self.assertNotEqual(s["company_dealer"], "03968287000136")
        self.assertEqual(s["revision_number"],1)

    def test_service_without_ordinal_remains_unclassified(self):
        e=event(stage=None,confidence='sem_numero')
        s=summarize_workshop([e],['CHASSIS-A'])
        self.assertEqual(s['candidate_os'],0)
        self.assertEqual(s['service_without_stage'],1)


if __name__=='__main__':
    unittest.main()
