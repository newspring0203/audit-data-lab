from pathlib import Path
import unittest
from src.audit_core import load_raw
from src.gl_core import build_journals, flattened_gl, check_journal_balance, trial_balance, ar_by_invoice

ROOT = Path(__file__).resolve().parents[1]
class TestGeneralLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = load_raw(ROOT / 'data' / 'raw')
        cls.headers, cls.lines = build_journals(cls.raw)
        cls.gl = flattened_gl(cls.headers, cls.lines)

    def test_counts_and_balances(self):
        self.assertEqual(len(self.headers), 21)
        self.assertEqual(len(self.lines), 42)
        self.assertTrue(all(r['check']=='정상' for r in check_journal_balance(self.headers, self.lines)))

    def test_sales_invoice_001_and_receipt(self):
        sale = [x for x in self.gl if x['entry_id']=='J-1001']
        payment = [x for x in self.gl if x['entry_id']=='JR-R-001']
        self.assertEqual([(x['account_code'], x['debit_krw'], x['credit_krw']) for x in sale],
                         [('1100', 1200000, 0), ('4010', 0, 1200000)])
        self.assertEqual([(x['account_code'], x['debit_krw'], x['credit_krw']) for x in payment],
                         [('1010', 1200000, 0), ('1100', 0, 1200000)])

    def test_duplicate_invoice_is_not_found_by_balancing(self):
        matching = [h for h in self.headers if h['invoice_id']=='INV-007' and h['source_type']=='SALE']
        self.assertEqual(len(matching), 2)
        self.assertTrue(all(x['check']=='정상' for x in check_journal_balance(self.headers,self.lines)))

    def test_trial_balance(self):
        tb = trial_balance(self.gl, 2025)
        self.assertEqual(sum(x['net_debit_krw'] for x in tb), sum(x['net_credit_krw'] for x in tb))
        # 사업이 2025/2026 두 해에 걸쳐 있으며 기초잔액·비용·세금 생략한 부분원장
        self.assertEqual([x for x in tb if x['account_code']=='4010'][0]['net_credit_krw'], 20860000)

    def test_unmatched_receipt(self):
        r = {x['invoice_id']: x for x in ar_by_invoice(self.gl)}
        self.assertLess(r['INV-012']['ar_balance_krw'], 0)
        self.assertEqual(r['INV-012']['ar_balance_krw'], -670000)

if __name__=='__main__': unittest.main()
