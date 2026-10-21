import json
import sys
import unittest
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

module = import_module("11_opendart_xbrl_analysis")

amount_or_none = module.amount_or_none
build_checks = module.build_checks
build_metrics = module.build_metrics
normalize_rows = module.normalize_rows
parse_xbrl_facts = module.parse_xbrl_facts

class Mission11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads((ROOT / 'data/mission11/demo_opendart_response.json').read_text(encoding='utf-8'))
        cls.rows = normalize_rows(payload, 'DEMO')
        cls.metrics = build_metrics(cls.rows, 2025)

    def test_amounts(self):
        self.assertEqual(amount_or_none('1,200,000'), 1200000)
        self.assertEqual(amount_or_none('(2,000)'), -2000)
        self.assertIsNone(amount_or_none('-'))

    def test_asset_equation(self):
        result = build_checks(self.metrics)
        self.assertEqual(result[0]['status'], 'PASS')
        self.assertEqual(result[1]['status'], 'PASS')

    def test_revenue_growth(self):
        checks = build_checks(self.metrics)
        self.assertEqual(checks[2]['status'], 'PASS')
        self.assertIn('+22.22%', checks[2]['reason'])

    def test_xbrl_context_and_unit(self):
        x = (ROOT / 'data/mission11/demo_xbrl_structure.xml').read_bytes()
        facts = parse_xbrl_facts(x, 'demo.xml')
        self.assertEqual(len(facts), 4)
        self.assertEqual(facts[0]['period_instant'], '2025-12-31')
        self.assertEqual(facts[-1]['period_start'], '2025-01-01')
        self.assertEqual(facts[-1]['unit_measure'], 'iso4217:KRW')

    def test_ambiguous_id_does_not_autosum(self):
        rows = self.rows + [next(x for x in self.rows if x['account_id']=='ifrs-full_Assets').copy()]
        m = build_metrics(rows, 2025)
        assets = next(x for x in m if x['metric']=='assets')
        self.assertIn('ambiguous', assets['match_status'])
        self.assertIsNone(assets['current_krw'])

if __name__ == '__main__':
    unittest.main()
