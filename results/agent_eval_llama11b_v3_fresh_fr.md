# Memo agent evaluation: nvidia: meta/llama-3.2-11b-vision-instruct

Language: fr. Scoring: in-process API (same code as the Lambda). Decision lines: 2% and 5% (assumption). Generated 2026-10-19 20:13. Writer settings: {'temperature': 0.0, 'max_tokens': 2500, 'timeout_s': 150.0}.

| Measure | Value |
|---|---|
| Loans | 20 |
| Accepted on the first try, with a 95% interval (the sample is small) | 18 of 20 = 90% (between 70% and 97%) |
| Memo written by the model and accepted (first try or rewrite), 95% interval | 19 of 20 = 95% (between 76% and 99%) |
| Accepted on the first try | 18 |
| Accepted after a rewrite | 1 |
| Backup memo (written by code) | 1 |
| of which the model's last memo had a problem of FORM only (headings, length) | 1 |
| Tries rejected for a SAFETY reason (number, decision, warning, promise), of all tries | 0 of 23 |
| Loans where the writer itself failed | 0 |
| Mean number of tries | 1.15 |
| Decisions | {'approve': 8, 'refer': 6, 'decline': 6} |
| Seconds per loan (mean, slowest) | 43.5, 177.0 |
| Complaints raised by the inspector | {'LENGTH': 4} |

| Case | Decision | Result | Tries | Seconds | Complaints per try |
|---|---|---|---|---|---|
| `g01` | approve | accepted | 1 | 16.3 | [[]] |
| `g02` | refer | accepted | 1 | 44.0 | [[]] |
| `g03` | approve | accepted | 1 | 18.1 | [[]] |
| `g04` | decline | accepted | 1 | 17.7 | [[]] |
| `g05` | refer | accepted | 1 | 18.4 | [[]] |
| `g06` | approve | accepted | 1 | 119.3 | [[]] |
| `g07` | approve | accepted | 1 | 20.1 | [[]] |
| `g08` | approve | accepted | 1 | 16.5 | [[]] |
| `g09` | approve | accepted | 1 | 30.3 | [[]] |
| `g10` | decline | accepted | 1 | 23.2 | [[]] |
| `g11` | refer | backup | 3 | 105.7 | [['LENGTH'], ['LENGTH'], ['LENGTH']] |
| `g12` | decline | accepted | 1 | 9.1 | [[]] |
| `g13` | refer | accepted | 1 | 16.5 | [[]] |
| `g14` | refer | accepted | 1 | 68.4 | [[]] |
| `g15` | decline | accepted | 1 | 14.1 | [[]] |
| `g16` | approve | accepted | 1 | 177.0 | [[]] |
| `g17` | decline | accepted | 1 | 76.4 | [[]] |
| `g18` | approve | accepted | 1 | 14.6 | [[]] |
| `g19` | decline | accepted | 1 | 13.4 | [[]] |
| `g20` | refer | accepted | 2 | 51.1 | [['LENGTH'], []] |

## Evidence for the loans that did not pass at once

What the inspector complained about on each try. The text the model wrote is kept in the JSON file.

### `g11` (refer, backup)
- try 1: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 3: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).

### `g20` (refer, accepted)
- try 1: [LENGTH] The memo has 265 words and the limit is 260: remove at least 25 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: accepted

