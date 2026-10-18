# Memo agent evaluation: pretend careful writer (not a language model)

Language: fr. Scoring: in-process API (same code as the Lambda). Decision lines: 2% and 5% (assumption). Generated 2026-10-18 21:14.

| Measure | Value |
|---|---|
| Loans | 15 |
| Accepted on the first try | 15 |
| Accepted after a rewrite | 0 |
| Backup memo (written by code) | 0 |
| Loans where the writer itself failed | 0 |
| Mean number of tries | 1.0 |
| Decisions | {'approve': 4, 'refer': 4, 'decline': 7} |
| Complaints raised by the inspector | none |

| Case | Decision | Result | Tries | Complaints per try |
|---|---|---|---|---|
| `01_prime_excellent` | approve | accepted | 1 | [[]] |
| `02_prime_purchase` | approve | accepted | 1 | [[]] |
| `03_good_cash_refinance` | approve | accepted | 1 | [[]] |
| `04_short_term_15_years` | approve | accepted | 1 | [[]] |
| `05_just_above_first_line` | refer | accepted | 1 | [[]] |
| `06_middle_of_the_refer_zone` | refer | accepted | 1 | [[]] |
| `07_just_below_second_line` | refer | accepted | 1 | [[]] |
| `08_just_above_second_line` | decline | accepted | 1 | [[]] |
| `09_golden_loan` | decline | accepted | 1 | [[]] |
| `10_weak_credit` | decline | accepted | 1 | [[]] |
| `11_very_weak_credit` | decline | accepted | 1 | [[]] |
| `12_outside_training_range` | decline | accepted | 1 | [[]] |
| `13_some_values_unknown` | decline | accepted | 1 | [[]] |
| `14_everything_unknown` | decline | accepted | 1 | [[]] |
| `15_long_term_40_years` | refer | accepted | 1 | [[]] |
