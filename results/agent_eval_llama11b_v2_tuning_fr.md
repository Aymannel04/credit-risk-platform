# Memo agent evaluation: nvidia: meta/llama-3.2-11b-vision-instruct

Language: fr. Scoring: in-process API (same code as the Lambda). Decision lines: 2% and 5% (assumption). Generated 2026-10-19 18:50. Writer settings: {'temperature': 0.0, 'max_tokens': 2500, 'timeout_s': 150.0}.

| Measure | Value |
|---|---|
| Loans | 15 |
| Accepted on the first try | 14 |
| Accepted after a rewrite | 1 |
| Backup memo (written by code) | 0 |
| Loans where the writer itself failed | 0 |
| Mean number of tries | 1.13 |
| Decisions | {'approve': 4, 'refer': 4, 'decline': 7} |
| Complaints raised by the inspector | {'LENGTH': 1, 'SECTIONS': 1} |

| Case | Decision | Result | Tries | Complaints per try |
|---|---|---|---|---|
| `01_prime_excellent` | approve | accepted | 1 | [[]] |
| `02_prime_purchase` | approve | accepted | 1 | [[]] |
| `03_good_cash_refinance` | approve | accepted | 1 | [[]] |
| `04_short_term_15_years` | approve | accepted | 1 | [[]] |
| `05_just_above_first_line` | refer | accepted | 1 | [[]] |
| `06_middle_of_the_refer_zone` | refer | accepted | 1 | [[]] |
| `07_just_below_second_line` | refer | accepted | 3 | [['LENGTH'], ['SECTIONS'], []] |
| `08_just_above_second_line` | decline | accepted | 1 | [[]] |
| `09_golden_loan` | decline | accepted | 1 | [[]] |
| `10_weak_credit` | decline | accepted | 1 | [[]] |
| `11_very_weak_credit` | decline | accepted | 1 | [[]] |
| `12_outside_training_range` | decline | accepted | 1 | [[]] |
| `13_some_values_unknown` | decline | accepted | 1 | [[]] |
| `14_everything_unknown` | decline | accepted | 1 | [[]] |
| `15_long_term_40_years` | refer | accepted | 1 | [[]] |

## Evidence for the loans that did not pass at once

What the inspector complained about on each try. The text the model wrote is kept in the JSON file.

### `07_just_below_second_line` (refer, accepted)
- try 1: [LENGTH] The memo has 276 words and the limit is 260: remove at least 36 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé Le score de cré
- try 3: accepted

