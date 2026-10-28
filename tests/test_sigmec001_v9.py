from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sigmec_parser import catalog_candidates, normalize_os, parse_sigmec
from src.revision_taxonomy import DEFAULT_CATALOG, possible_revision_numbers


def fixture(os_number="00361899", dealer="0091342", codes=("0010C21",)):
    c = list(" " * 1324)
    c[:2] = "#C"
    c[2:10] = os_number
    c[10:17] = dealer
    c[50:58] = "20260313"
    c[114:122] = "20241007"
    c[122:130] = "20250121"
    lines = ["#A1234567", "#B01", "".join(c), "#D001000"]
    for code in codes:
        e = list(" " * 292)
        e[:2] = "#E"
        e[2:10] = os_number
        e[10:17] = dealer
        e[26:97] = "REVISAO PROGRAMADA".ljust(71)
        e[97:104] = code
        e[105:145] = "1A REVISAO FLEX - KM OU TEMPO".ljust(40)
        lines.append("".join(e))
        lines.append("#F" + " " * 90)
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


class SigmecV9Tests(unittest.TestCase):
    def test_reader_fixed_width(self):
        rows, stats = parse_sigmec(fixture())
        self.assertEqual(stats["orders"], 1)
        self.assertEqual(rows[0]["os_number"], "00361899")
        self.assertEqual(rows[0]["dealer_code"], "0091342")
        self.assertEqual(rows[0]["interventions"][0]["code"], "0010C21")

    def test_multiple_interventions_single_order(self):
        rows, stats = parse_sigmec(fixture(codes=("0010C21", "0010F36")))
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["interventions"]), 2)
        self.assertEqual(stats["interventions"], 2)

    def test_invalid_e_does_not_link_other_order(self):
        data = fixture()
        marker = b"#E00361899"
        data = data.replace(marker, b"#E00361898")
        rows, stats = parse_sigmec(data)
        self.assertEqual(rows[0]["interventions"], [])
        self.assertEqual(stats["orphan_e_lines"], 1)

    def test_catalog_matches_specific_code_only(self):
        data = fixture(codes=("0010A14", "0010C21", "0010T12"))
        rows, _ = parse_sigmec(data)
        self.assertEqual(catalog_candidates(rows, dict(DEFAULT_CATALOG))["revision_codes"], 1)

    def test_normalize_leading_zero(self):
        self.assertEqual(normalize_os("00361899"), normalize_os("361899"))
        self.assertEqual(normalize_os("ABC"), "")

    def test_ambiguous_flex_diesel_not_forced_without_fuel(self):
        desc = dict(DEFAULT_CATALOG)["0010F38"]
        self.assertEqual(possible_revision_numbers(desc, "ARGO DRIVE 1.0"), [2, 4])
        self.assertEqual(possible_revision_numbers(desc, "ARGO FLEX"), [4])
        self.assertEqual(possible_revision_numbers(desc, "DUCATO DIESEL"), [2])

    def test_header_required(self):
        with self.assertRaises(ValueError):
            parse_sigmec(b"not sigmec")

    def test_input_duplicate_digest_stable(self):
        self.assertEqual(hashlib.sha256(fixture()).digest(), hashlib.sha256(fixture()).digest())


if __name__ == "__main__":
    unittest.main()
