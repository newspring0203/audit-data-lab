import sys
import unittest
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

module = import_module("10_financial_statement_tieout")

build_workpaper = module.build_workpaper
expected_fs_lines = module.expected_fs_lines



class TestMission10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.tb, cls.statements, cls.checks, cls.exceptions = build_workpaper()
        cls.by_id = {c['check_id']: c for c in cls.checks}

    def test_balanced_trial_balance(self):
        self.assertEqual(sum(x['closing_debit_krw'] for x in self.tb),
                         sum(x['closing_credit_krw'] for x in self.tb))

    def test_2026_receipts_are_excluded(self):
        # 2025 GL에 있는 보통예금 잔액: 기존 2025 입금 365만+신규 시나리오 순액 690만
        r = next(x for x in self.tb if x['account_code'] == '1010')
        self.assertEqual(r['closing_debit_krw'], 10550000)

    def test_gl_revenue_and_derived_profit(self):
        expected = expected_fs_lines(self.tb)
        self.assertEqual(expected['revenue'], 20860000)
        self.assertEqual(expected['net_income'], 16960000)
        self.assertEqual(expected['total_assets'], expected['total_liabilities_equity'])
        self.assertEqual(expected['total_assets'], 33460000)

    def test_five_flags(self):
        self.assertEqual({r['검토번호'] for r in self.exceptions}, {
            'FOOT_TOTAL_ASSETS', 'GL_REVENUE', 'GL_NET_INCOME',
            'CROSS_PROFIT', 'BS_EQUATION',
        })
        self.assertEqual(len(self.checks), 28)

    def test_root_causes_not_double_counted_as_real_errors(self):
        self.assertEqual(self.by_id['GL_REVENUE']['차이_원'], -200000)
        self.assertEqual(self.by_id['FOOT_TOTAL_ASSETS']['차이_원'], -100000)
        # 5개 탐지는 두 개의 의도된 오기에서 파생된 다중 검증 신호.
        self.assertEqual(self.by_id['CROSS_PROFIT']['차이_원'], -200000)


if __name__ == '__main__':
    unittest.main()
