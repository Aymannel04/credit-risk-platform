# Memo agent evaluation: nvidia: meta/llama-3.2-11b-vision-instruct

Language: fr. Scoring: in-process API (same code as the Lambda). Decision lines: 2% and 5% (assumption). Generated 2026-10-19 17:54.

| Measure | Value |
|---|---|
| Loans | 15 |
| Accepted on the first try, with a 95% interval (the sample is small) | 11 of 15 = 73% (between 48% and 89%) |
| Memo written by the model and accepted (first try or rewrite), 95% interval | 13 of 15 = 87% (between 62% and 96%) |
| Accepted on the first try | 11 |
| Accepted after a rewrite | 2 |
| Backup memo (written by code) | 2 |
| of which the model's last memo had a problem of FORM only (headings, length) | not recorded |
| Tries rejected for a SAFETY reason (number, decision, warning, promise), of all tries | not recorded of not recorded |
| Loans where the writer itself failed | 0 |
| Mean number of tries | 1.53 |
| Decisions | {'approve': 4, 'refer': 4, 'decline': 7} |
| Seconds per loan (mean, slowest) | not recorded, not recorded |
| Complaints raised by the inspector | {'LENGTH': 7, 'NUMBER_NOT_IN_FACTS': 1, 'SECTIONS': 6} |

| Case | Decision | Result | Tries | Seconds | Complaints per try |
|---|---|---|---|---|---|
| `01_prime_excellent` | approve | accepted | 1 |  | [[]] |
| `02_prime_purchase` | approve | accepted | 1 |  | [[]] |
| `03_good_cash_refinance` | approve | accepted | 3 |  | [['NUMBER_NOT_IN_FACTS'], ['SECTIONS'], []] |
| `04_short_term_15_years` | approve | accepted | 1 |  | [[]] |
| `05_just_above_first_line` | refer | backup | 3 |  | [['LENGTH'], ['LENGTH', 'SECTIONS'], ['LENGTH', 'SECTIONS']] |
| `06_middle_of_the_refer_zone` | refer | accepted | 1 |  | [[]] |
| `07_just_below_second_line` | refer | backup | 3 |  | [['LENGTH'], ['LENGTH', 'SECTIONS'], ['LENGTH', 'SECTIONS']] |
| `08_just_above_second_line` | decline | accepted | 1 |  | [[]] |
| `09_golden_loan` | decline | accepted | 1 |  | [[]] |
| `10_weak_credit` | decline | accepted | 1 |  | [[]] |
| `11_very_weak_credit` | decline | accepted | 3 |  | [['LENGTH'], ['SECTIONS'], []] |
| `12_outside_training_range` | decline | accepted | 1 |  | [[]] |
| `13_some_values_unknown` | decline | accepted | 1 |  | [[]] |
| `14_everything_unknown` | decline | accepted | 1 |  | [[]] |
| `15_long_term_40_years` | refer | accepted | 1 |  | [[]] |
