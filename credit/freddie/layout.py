"""Column layout of the Freddie Mac Single-Family Loan-Level sample files.

Source: General User Guide (January 2026), checked against the real 2016 sample file on
2026-10-09. The real files differ slightly from the guide:
  - origination: 31 fields (the guide lists 32; servicer name and MI cancellation moved to the
    performance file; the last field is always 9999 in the 2016 sample and is unused);
  - performance: 35 fields (the guide lists 32; fields 33-35 are MI cancellation indicator,
    servicer name and an unused amount).
Files are pipe-delimited with no header row.
"""

ORIGINATION_COLUMNS = [
    "credit_score",
    "first_payment_date",
    "first_time_homebuyer",
    "maturity_date",
    "msa",
    "mi_pct",
    "n_units",
    "occupancy",
    "cltv",
    "dti",
    "orig_upb",
    "ltv",
    "int_rate",
    "channel",
    "ppm_flag",
    "amort_type",
    "state",
    "property_type",
    "zip3",
    "loan_seq",
    "purpose",
    "orig_term",
    "n_borrowers",
    "seller_name",
    "super_conforming",
    "pre_relief_loan_seq",
    "program_indicator",
    "relief_refi",
    "property_valuation_method",
    "io_indicator",
    "unused_31",
]

PERFORMANCE_COLUMNS = [
    "loan_seq",
    "report_period",
    "current_upb",
    "delinq_status",
    "loan_age",
    "months_remaining",
    "defect_settlement_date",
    "modification_flag",
    "zero_balance_code",
    "zero_balance_date",
    "current_int_rate",
    "current_non_int_upb",
    "ddlpi",
    "mi_recoveries",
    "net_sale_proceeds",
    "non_mi_recoveries",
    "total_expenses",
    "legal_costs",
    "maintenance_costs",
    "taxes_insurance",
    "misc_expenses",
    "actual_loss",
    "cum_mod_cost",
    "step_mod_indicator",
    "payment_deferral_flag",
    "eltv",
    "zero_balance_removal_upb",
    "delinquent_accrued_interest",
    "disaster_flag",
    "borrower_assist_code",
    "current_month_mod_cost",
    "interest_bearing_upb",
    "mi_cancel_indicator",
    "servicer_name",
    "unused_35",
]

assert len(ORIGINATION_COLUMNS) == 31
assert len(PERFORMANCE_COLUMNS) == 35
