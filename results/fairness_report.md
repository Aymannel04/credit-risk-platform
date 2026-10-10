# Fairness slices (scorecard; line = approve if PD <= 0.1471)

No sex, race or age exists in these data: this is an analysis of differences between the groups that do exist, NOT a legal fairness certification. Flags: approval = adverse impact ratio < 0.80; calibration = the 95% interval of predicted/observed excludes 1 (needs >= 30 defaults).

## validation

### first_time_homebuyer

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| N | 16,741 | 346 | 2.07% | 1.93% | 97.6% | 1.0x | 0.93 (0.84-1.04) |  |
| Y | 2,384 | 45 | 1.89% | 2.80% | 97.1% | 1.2x | 1.48 (1.15-2.09) | CALIBRATION |

### occupancy

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| P | 16,893 | 336 | 1.99% | 1.98% | 97.6% | 1.0x | 1.00 (0.90-1.12) |  |
| I | 1,412 | 39 | 2.76% | 2.77% | 96.6% | 1.4x | 1.00 (0.76-1.46) |  |
| S | 824 | 16 | 1.94% | 1.93% | 97.5% | 1.1x | 0.99 |  |

### purpose

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| P | 7,554 | 140 | 1.85% | 2.48% | 97.0% | 1.8x | 1.34 (1.15-1.61) | CALIBRATION |
| N | 6,512 | 109 | 1.67% | 1.41% | 98.4% | 1.0x | 0.84 (0.71-1.03) |  |
| C | 5,063 | 142 | 2.80% | 2.18% | 97.1% | 1.8x | 0.78 (0.67-0.93) | CALIBRATION |

### property_type

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| SF | 13,310 | 281 | 2.11% | 2.03% | 97.4% | 1.3x | 0.96 (0.86-1.09) |  |
| PU | 4,320 | 72 | 1.67% | 1.87% | 98.0% | 1.0x | 1.12 (0.91-1.46) |  |
| CO | 1,388 | 33 | 2.38% | 2.58% | 96.5% | 1.8x | 1.09 (0.81-1.65) |  |

### channel

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| R | 10,046 | 130 | 1.29% | 1.31% | 99.2% | 1.0x | 1.01 (0.86-1.22) |  |
| C | 5,509 | 78 | 1.42% | 1.53% | 98.8% | 1.4x | 1.08 (0.88-1.38) |  |
| B | 2,146 | 76 | 3.54% | 3.10% | 95.7% | 5.1x | 0.87 (0.71-1.13) |  |
| T | 1,428 | 107 | 7.49% | 7.53% | 83.4% | 19.6x | 1.00 (0.84-1.24) |  |

### state

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| other states | 9,537 | 183 | 1.92% | 1.94% | 97.7% | 3.2x | 1.01 (0.88-1.18) |  |
| CA | 2,718 | 54 | 1.99% | 1.58% | 98.5% | 2.2x | 0.79 (0.63-1.08) |  |
| TX | 1,180 | 20 | 1.69% | 2.56% | 97.1% | 4.1x | 1.51 |  |
| IL | 1,103 | 23 | 2.09% | 2.34% | 97.5% | 3.6x | 1.12 |  |
| FL | 958 | 50 | 5.22% | 5.07% | 90.2% | 14.1x | 0.97 (0.76-1.34) |  |
| OH | 629 | 5 | 0.79% | 1.09% | 99.2% | 1.1x | 1.37 |  |
| NY | 617 | 23 | 3.73% | 2.73% | 95.8% | 6.1x | 0.73 |  |
| VA | 607 | 7 | 1.15% | 1.52% | 98.2% | 2.6x | 1.32 |  |
| WA | 606 | 14 | 2.31% | 1.36% | 98.7% | 1.9x | 0.59 |  |
| NC | 599 | 7 | 1.17% | 1.62% | 97.8% | 3.1x | 1.39 |  |
| CO | 575 | 5 | 0.87% | 1.06% | 99.3% | 1.0x | 1.22 |  |

## later years (2019 + 2022 exams pooled; post-exam diagnostic)

### first_time_homebuyer

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| N | 73,905 | 965 | 1.31% | 1.77% | 99.2% | 1.0x | 1.35 (1.27-1.45) | CALIBRATION |
| Y | 25,883 | 357 | 1.38% | 2.33% | 98.8% | 1.5x | 1.69 (1.53-1.88) | CALIBRATION |

### occupancy

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| P | 89,022 | 1239 | 1.39% | 1.91% | 99.1% | 1.0x | 1.38 (1.30-1.46) | CALIBRATION |
| I | 7,470 | 56 | 0.75% | 2.03% | 99.1% | 1.0x | 2.70 (2.14-3.66) | CALIBRATION |
| S | 3,296 | 27 | 0.82% | 1.64% | 99.0% | 1.1x | 2.00 |  |

### purpose

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| P | 61,034 | 720 | 1.18% | 2.03% | 98.9% | 4.2x | 1.72 (1.60-1.86) | CALIBRATION |
| C | 22,904 | 428 | 1.87% | 2.10% | 99.0% | 3.9x | 1.12 (1.03-1.24) | CALIBRATION |
| N | 15,850 | 174 | 1.10% | 1.19% | 99.7% | 1.0x | 1.09 (0.95-1.28) |  |

### property_type

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| SF | 61,829 | 882 | 1.43% | 1.93% | 99.1% | 1.0x | 1.35 (1.27-1.45) | CALIBRATION |
| PU | 28,896 | 324 | 1.12% | 1.79% | 99.1% | 1.0x | 1.60 (1.44-1.79) | CALIBRATION |
| CO | 8,190 | 101 | 1.23% | 2.18% | 98.6% | 1.7x | 1.77 (1.48-2.20) | CALIBRATION |
| MH | 675 | 14 | 2.07% | 2.46% | 98.4% | 1.9x | 1.18 |  |

### channel

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| R | 52,709 | 688 | 1.31% | 1.66% | 99.5% | 1.0x | 1.27 (1.18-1.37) | CALIBRATION |
| C | 33,472 | 440 | 1.31% | 1.91% | 99.1% | 1.6x | 1.45 (1.33-1.60) | CALIBRATION |
| B | 13,607 | 194 | 1.43% | 2.91% | 97.5% | 4.7x | 2.04 (1.79-2.38) | CALIBRATION |

### state

| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |
|---|---|---|---|---|---|---|---|---|
| other states | 48,594 | 587 | 1.21% | 1.61% | 99.5% | 4.8x | 1.33 (1.23-1.45) | CALIBRATION |
| CA | 9,914 | 140 | 1.41% | 1.50% | 99.6% | 4.1x | 1.06 (0.91-1.27) |  |
| TX | 8,590 | 120 | 1.40% | 1.82% | 99.4% | 6.0x | 1.30 (1.11-1.59) | CALIBRATION |
| FL | 7,609 | 142 | 1.87% | 4.07% | 95.5% | 41.8x | 2.18 (1.87-2.61) | CALIBRATION |
| IL | 4,263 | 64 | 1.50% | 2.31% | 98.8% | 11.6x | 1.54 (1.24-2.04) | CALIBRATION |
| OH | 3,739 | 47 | 1.26% | 1.42% | 99.9% | 1.0x | 1.13 (0.88-1.58) |  |
| MI | 3,533 | 52 | 1.47% | 2.30% | 98.6% | 13.0x | 1.56 (1.23-2.15) | CALIBRATION |
| AZ | 3,501 | 45 | 1.29% | 2.14% | 99.2% | 7.7x | 1.66 (1.29-2.35) | CALIBRATION |
| GA | 3,462 | 56 | 1.62% | 2.66% | 98.5% | 13.8x | 1.64 (1.30-2.23) | CALIBRATION |
| NC | 3,324 | 28 | 0.84% | 1.61% | 99.6% | 3.7x | 1.92 |  |
| PA | 3,259 | 41 | 1.26% | 1.79% | 99.3% | 6.6x | 1.42 (1.09-2.05) | CALIBRATION |
