-- SQLite에서 실행 (python3 run_gl.py 실행 후 reports/general_ledger.db)
-- 1. 전표별 차변 대변 합계 대사
SELECT entry_id, SUM(debit_krw) AS debit, SUM(credit_krw) AS credit,
       SUM(debit_krw)-SUM(credit_krw) AS diff
FROM general_ledger
GROUP BY entry_id
HAVING diff != 0;

-- 2. 2025년 계정별 시산표의 기초가 되는 발생액
SELECT account_code, account_name,
       SUM(debit_krw) AS debit_turnover, SUM(credit_krw) AS credit_turnover,
       SUM(debit_krw)-SUM(credit_krw) AS net_debit
FROM general_ledger
WHERE fiscal_year = 2025
GROUP BY account_code, account_name
ORDER BY account_code;

-- 3. 하나의 청구서를 참조하는 매출전표 수: 중복 후보
SELECT invoice_id, COUNT(DISTINCT entry_id) AS sales_entries
FROM general_ledger
WHERE source_type='SALE' AND account_code='4010'
GROUP BY invoice_id
HAVING sales_entries > 1;

-- 4. 매출채권 거래별 잔액: 음수라면 연결 누락/선수금 등을 검토
SELECT invoice_id, SUM(debit_krw-credit_krw) AS ar_balance
FROM general_ledger
WHERE account_code='1100'
GROUP BY invoice_id
HAVING ar_balance < 0;
