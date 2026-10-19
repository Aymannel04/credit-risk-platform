# Memo agent evaluation: nvidia: meta/llama-3.2-11b-vision-instruct

Language: fr. Scoring: in-process API (same code as the Lambda). Decision lines: 2% and 5% (assumption). Generated 2026-10-19 19:18. Writer settings: {'temperature': 0.0, 'max_tokens': 2500, 'timeout_s': 150.0}.

| Measure | Value |
|---|---|
| Loans | 20 |
| Accepted on the first try, with a 95% interval (the sample is small) | 12 of 20 = 60% (between 39% and 78%) |
| Memo written by the model and accepted (first try or rewrite), 95% interval | 15 of 20 = 75% (between 53% and 89%) |
| Accepted on the first try | 12 |
| Accepted after a rewrite | 3 |
| Backup memo (written by code) | 5 |
| of which the model's last memo had a problem of FORM only (headings, length) | not recorded |
| Tries rejected for a SAFETY reason (number, decision, warning, promise), of all tries | not recorded of not recorded |
| Loans where the writer itself failed | 0 |
| Mean number of tries | 1.8 |
| Decisions | {'approve': 12, 'decline': 5, 'refer': 3} |
| Seconds per loan (mean, slowest) | not recorded, not recorded |
| Complaints raised by the inspector | {'LENGTH': 15, 'NUMBER_NOT_IN_FACTS': 2, 'SECTIONS': 9} |

| Case | Decision | Result | Tries | Seconds | Complaints per try |
|---|---|---|---|---|---|
| `h01` | approve | backup | 3 |  | [['LENGTH'], ['LENGTH', 'SECTIONS'], ['LENGTH']] |
| `h02` | decline | backup | 3 |  | [['LENGTH'], ['LENGTH', 'SECTIONS'], ['LENGTH']] |
| `h03` | approve | accepted | 1 |  | [[]] |
| `h04` | approve | accepted | 1 |  | [[]] |
| `h05` | refer | backup | 3 |  | [['LENGTH'], ['LENGTH', 'SECTIONS'], ['LENGTH']] |
| `h06` | decline | accepted | 1 |  | [[]] |
| `h07` | decline | accepted | 3 |  | [['LENGTH'], ['SECTIONS'], []] |
| `h08` | approve | accepted | 1 |  | [[]] |
| `h09` | approve | accepted | 1 |  | [[]] |
| `h10` | refer | accepted | 3 |  | [['LENGTH'], ['SECTIONS'], []] |
| `h11` | approve | accepted | 1 |  | [[]] |
| `h12` | decline | accepted | 3 |  | [['LENGTH'], ['SECTIONS'], []] |
| `h13` | approve | accepted | 1 |  | [[]] |
| `h14` | approve | accepted | 1 |  | [[]] |
| `h15` | refer | backup | 3 |  | [['LENGTH'], ['LENGTH', 'SECTIONS'], ['LENGTH']] |
| `h16` | approve | accepted | 1 |  | [[]] |
| `h17` | approve | accepted | 1 |  | [[]] |
| `h18` | approve | accepted | 1 |  | [[]] |
| `h19` | decline | accepted | 1 |  | [[]] |
| `h20` | approve | backup | 3 |  | [['NUMBER_NOT_IN_FACTS'], ['NUMBER_NOT_IN_FACTS', 'SECTIONS'], ['SECTIONS']] |

## Evidence for the loans that did not pass at once

What the inspector complained about on each try. The text the model wrote is kept in the JSON file.

### `h01` (approve, backup)
- try 1: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé Le score de cré; [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 3: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).

### `h02` (decline, backup)
- try 1: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé Le score de cré; [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 3: [LENGTH] The memo has 264 words and the limit is 260: remove at least 24 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).

### `h05` (refer, backup)
- try 1: [LENGTH] The memo has 265 words and the limit is 260: remove at least 25 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé La probabilité ; [LENGTH] The memo has 265 words and the limit is 260: remove at least 25 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 3: [LENGTH] The memo has 265 words and the limit is 260: remove at least 25 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).

### `h07` (decline, accepted)
- try 1: [LENGTH] The memo has 270 words and the limit is 260: remove at least 30 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé La probabilité 
- try 3: accepted

### `h10` (refer, accepted)
- try 1: [LENGTH] The memo has 281 words and the limit is 260: remove at least 41 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé Le prêt a été é
- try 3: accepted

### `h12` (decline, accepted)
- try 1: [LENGTH] The memo has 275 words and the limit is 260: remove at least 35 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé La probabilité 
- try 3: accepted

### `h15` (refer, backup)
- try 1: [LENGTH] The memo has 261 words and the limit is 260: remove at least 21 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé Le score de cré; [LENGTH] The memo has 261 words and the limit is 260: remove at least 21 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).
- try 3: [LENGTH] The memo has 261 words and the limit is 260: remove at least 21 words of your own text (the system's 'Loan data' section and the fixed sentences cannot be shortened).

### `h20` (approve, backup)
- try 1: [NUMBER_NOT_IN_FACTS] These numbers are not on the fact sheet: -17,6, -34,2, -52,1, -6,1. Copy numbers exactly as written on the fact sheet and never compute a new one.
- try 2: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé La probabilité ; [NUMBER_NOT_IN_FACTS] These numbers are not on the fact sheet: -17,6, -34,2, -52,1, -6,1. Copy numbers exactly as written on the fact sheet and never compute a new one.
- try 3: [SECTIONS] Use exactly these five headings, in this order, each on its own line starting with '## ': Résumé | Analyse du risque | Raisons principales | Recommandation | Limites. You wrote: Résumé La probabilité 

