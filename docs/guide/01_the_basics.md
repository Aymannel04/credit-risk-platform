# 1. The basics: loans, risk and money

## 1.1 A mortgage in one story

You want to buy a house for 200,000. You have 40,000 saved. The bank lends you the other 160,000.
You promise to pay it back in small monthly payments over 30 years, plus **interest** (the price of borrowing).
The loan is **secured** by the house: if you stop paying, the bank can take the house and sell it.

Two numbers every lender looks at:

- **LTV (loan-to-value)** = loan / house value. Here 160,000 / 200,000 = **80%**. The more you borrow compared with the
  house value, the riskier it is for the bank (you have less of your own money in it, and a small drop in house prices
  can wipe out the bank's safety margin).
- **DTI (debt-to-income)** = your monthly debt payments / your monthly income. If you earn 5,000 and your debts
  (mortgage, car, cards) cost 2,000 a month, DTI = **40%**. Above about 43-45% is considered stretched.

And the **credit score** (here the FICO score, 300 to 850): a number made by a third party that summarises how reliably
you repaid past debts. Higher is safer. In our data, the safest group (above 766) defaulted 0.4% of the time, the riskiest
(under 663) 11.5%: nearly **30 times more**.

## 1.2 What is a default?

A **default** means a borrower stops paying seriously. The ladder of trouble:

```
on time  ->  30 days late  ->  60 days late  ->  90+ days late  ->  foreclosure  ->  house sold (maybe at a loss)
 (status 0)   (status 1)       (status 2)        (status 3+)         (bank takes it)   (REO = bank owns the property)
```

Freddie Mac does **not** give a ready-made "default" column. So **we had to define it ourselves** (this is a real decision
that you must be able to explain). Our definition, called **B**:

> Within the first **24 months** of the loan, the loan is **90+ days late** *while no payment-relief plan is active*,
> **or** it ends with a loss event (short sale, charge-off, house taken and sold...).

Why the "no relief plan" part? During COVID, the government let many people **pause** payments (**forbearance**).
They show as "90 days late" but they are not real defaults. Without this rule, the 2019 loans looked as risky as the
2008 crisis (4.6% "defaults") when most were just paused (1.3% with our rule).

Why 24 months? A short window misses late defaults; a long one needs very old loans. 24 months is a common compromise.

## 1.3 The three letters of credit risk: PD, LGD, EAD

| Letter | Name | Plain meaning | Example |
|---|---|---|---|
| **PD** | Probability of Default | How likely is it that this borrower defaults? | 2% |
| **EAD** | Exposure at Default | How much money is at risk? (we use the loan amount) | 200,000 |
| **LGD** | Loss Given Default | If it defaults, what share of the money is lost? | 25% |

**Expected loss = PD x LGD x EAD**. Example: 2% x 25% x 200,000 = **1,000**. A bank sets aside about that much per
loan like this, and charges interest that covers it. That is why a **trustworthy PD** matters: it is multiplied by
real money.

### What we found about LGD in the real data (very important)

Most "defaults" by our definition **recover**: the borrower catches up or the loan is paid off. Only some end in a loss.

| Loans from | Of 100 flagged "defaults", how many ended in a real loss? | Money lost per flagged loan (as % of the loan) |
|---|---|---|
| 2008 (crisis) | 47 | **20.1%** |
| 2012 | 27 | 4.4% |
| 2016 | 11 | 1.1% |
| 2019 | 4 | 0.4% (still incomplete: house sales take years) |
| 2022 | 7 | 0.5% (incomplete) |

In a crisis, house prices fall, sales do not cover the loan, and losses are large. In calm years, losses are small.
So **the money at stake depends on the economy**, not only on the borrower.

## 1.4 Words about the data

- **Origination** = the day the loan is created. The **origination file** is the loan's **ID card**: one row per loan,
  with facts known on day one (score, DTI, LTV, interest rate, state...).
- **Performance file** = the loan's **monthly diary**: one row per month (what is still owed, was it late, did it end).
  One loan has about 68 rows on average (some loans end early when the borrower pays off or refinances).
- **Vintage** = the year the loans were created, like the year of a wine. Vintages behave differently (2008 vs 2016).
- **Relief refinance (HARP)** = a government programme after 2008 for people who owed almost as much as their house was
  worth. A special group; we exclude it (one third of our 2012 sample).
- **Seasoned / modified loan** = a loan that was already old when Freddie Mac bought it, or whose terms were changed.
  Its "month 1" is not its real beginning. We exclude them (under 0.6% of the data).
- **Interest-rate spread** = a loan's rate minus the normal rate of the same quarter. Rates were 6% in 2008 and 3.6%
  in 2012 for everybody; what matters for risk is whether *this* borrower paid **more than others that quarter**
  (because the lender saw extra risk). The raw rate would only tell us which year it is.

## 1.5 The big picture of "scoring"

```
     facts on day one          the model             a number
  (score, DTI, LTV, ...)  --->  scorecard  --->  PD  (and a score in points)
                                                   |
                          + loss amount (LGD) ---> expected loss ---> approve? price? how much to set aside?
```

Before the loan is approved we only know the ID card. Anything from the diary is the **future**; using it to
predict the same future would be cheating (called **leakage**, explained in the next file).
