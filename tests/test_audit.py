import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.audit_core import analyze_files

class AuditCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.register, cls.exceptions = analyze_files(ROOT / "data/raw")
        cls.found = {(r["invoice_id"],r["rule_id"]) for r in cls.exceptions}

    def test_five_intended_exception_cases(self):
        expected={
            ("INV-006","R04_CUTOFF"),
            ("INV-007","R01_DUPLICATE"),
            ("INV-008","R03_NO_DELIVERY"),
            ("INV-009","R02_AMOUNT"),
            ("INV-012","R05_NOT_BOOKED"),
        }
        self.assertEqual(self.found,expected)

    def test_clean_transaction(self):
        self.assertFalse(any(r["invoice_id"]=="INV-001" for r in self.exceptions))

    def test_partial_payment_not_accounting_error(self):
        # INV-003은 300만원 청구, 150만원 입금. 매출 오류로 판정하지 않는다.
        row=next(r for r in self.register if r["invoice_id"]=="INV-003")
        self.assertEqual(row["invoice_minus_receipts_krw"],1500000)
        self.assertFalse(any(r["invoice_id"]=="INV-003" for r in self.exceptions))

    def test_invoice_012_reverse_matching(self):
        row=next(r for r in self.register if r["invoice_id"]=="INV-012")
        self.assertEqual(row["erp_entry_count"],0)

if __name__=="__main__":
    unittest.main()
