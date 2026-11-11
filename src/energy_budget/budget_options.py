"""Autumn Budget 2026: the energy measures in the baseline, and further options.

Bills. Each household's annual electricity and gas kWh come from the
certified Microcosm UK export and are costed quarter by quarter: kWh x unit
rate on that quarter's share of annual use (Ofgem's seasonal profile, 75% of
gas and 57% of electricity in October-March) plus the quarter's standing
charge. Households not connected to a fuel pay no standing charge for it.
The equal-quarter profile is reported as a sensitivity.

Baseline: post-Budget law at forecast prices. Prices are as published or
forecast (``config.PRICE_PATH``); electricity VAT follows the law for each
quarter and nation (``config.ELEC_VAT["post_budget"]``): 0% in Great
Britain from October 2026 to June 2027 and in Northern Ireland from April to
June 2027, 5% otherwise. The Household Energy Payment (£100 to households in
council tax bands A-D in England in 2026-27) comes from policyengine-uk,
which counts it in household and HBAI income.

Each Budget measure enters once. The VAT extension enters only through the
tariffs: no simulation changes a VAT parameter, so policyengine-uk's
``vat_change`` is zero everywhere (checked) and the model's own energy VAT
never reaches household income. The payment enters only through the model's
household income: bills are not reduced by it.

Counterfactual for the Budget measures ("pre_budget"): the same prices,
data and policies, with no Household Energy Payment and electricity VAT as
under SI 2026/987 alone (5% from April 2027 in Great Britain, 5% throughout
in Northern Ireland).

Options. The targeted discount (RF, simplified), Warm Home Discount top-up,
Cost of Living Payment and £400 payment are PolicyEngine reforms against the
post-Budget baseline. The cap freeze, the further VAT extension and levy
removal are price cuts costed from each household's bills, outside HBAI
income.
"""

from __future__ import annotations

import functools
import gc

import numpy as np
import pandas as pd

from .baseline import _build_simulation, weighted_mean
from .bills import FUELS, fuel_bill_for_profile, typical_bill
from .config import (
    BASELINE_LAW,
    CONSUMPTION_PROFILE,
    COUNTERFACTUAL_LAW,
    CURRENT_CAP,
    HEP_PARAMETER,
    NEW_TDCV,
    TDCV_ELEC_KWH,
    TDCV_GAS_KWH,
)
from .prices import HELD_QUARTERS, year_quarters

VAT = 0.05
WHD_TOP_UP = 100
# Moving the remaining policy levies (the last 25% of the Renewables
# Obligation and Feed-in Tariffs) to taxation: "as much as £120" off a
# typical bill, costing "as much as £3.2bn" (Guardian, 6 Oct 2026; FT,
# 11 Oct 2026). Levies sit on electricity, so each household's electricity
# bill falls by the share that takes £120 off the typical electricity bill.
LEVY_SAVING_TYPICAL = 120

TARIFF_NOTE = (
    "Every household is modelled on the capped variable tariff (Ofgem GB "
    "direct-debit averages). Around 35% of households are on fixed tariffs "
    "and will not see the October 2026 cap rise (Ofgem); tariff type, payment "
    "method and contract expiry are not modelled, so no correction for fixed "
    "tariffs is applied. Northern Ireland is costed on GB prices as a proxy."
)
TARIFF_NOTE_LINK = (
    "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026"
)

WHD_OFFICIAL_HOUSEHOLDS_M = 6.0
# Warm Home Discount receipt rates: around 85% of Pension Credit households and
# 70% of other qualifying households go on to receive the rebate (DESNZ,
# Continuing the Warm Home Discount 2026-2031: final stage impact assessment,
# DESNZ002(F)-26-EAC, 30 January 2026, para. 40, p. 11; Table 8 applies the
# same rates to Scotland). Drawn per household with the same hash as
# policyengine-uk#2616.
WHD_RECEIPT_RATE_PENSION_CREDIT = 0.85
WHD_RECEIPT_RATE_OTHER = 0.70
# The impact assessment's low and high sensitivities for the other-benefits
# rate (para. 105, Table 13).
WHD_OTHER_RATE_SENSITIVITIES = (0.60, 0.80)
WHD_IA_SENSITIVITY_LINK = (
    "https://assets.publishing.service.gov.uk/media/6978a8b51c24881f40a4d675/"
    "continuing-the-warm-home-discount-scheme-impact-assessment.pdf#page=29"
)
WHD_IA_LINK = (
    "https://assets.publishing.service.gov.uk/media/6978a8b51c24881f40a4d675/"
    "continuing-the-warm-home-discount-scheme-impact-assessment.pdf#page=11"
)
WHD_LINKS = [
    "https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-england-and-wales",
    "https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-scotland",
]
RF_LINK = "https://www.resolutionfoundation.org/publications/billing-me-softly/"
RF_ASSUMPTIONS = [
    (
        "A flat £175 per eligible household, not RF's discount on gas and electricity "
        "unit rates (£175 is RF's average per eligible household)."
    ),
    "The income test uses annual income, not the previous three months' income.",
    (
        "Full take-up: every eligible household receives it, including those that "
        "would have to self-declare."
    ),
]
NOT_HBAI = "Price cut, costed from bills; not in HBAI income, so no poverty effect."
BUDGET_COUNTERFACTUAL = (
    "Same prices, data and policies without the Budget's energy measures: no "
    "Household Energy Payment, and electricity VAT as under SI 2026/987 alone "
    "(5% from April 2027 in Great Britain, 5% throughout in Northern Ireland)."
)


def _quarters(year, is_ni_household, law):
    return year_quarters(year, "NI" if is_ni_household else "GB", law)


def typical(year, profile=CONSUMPTION_PROFILE, law=BASELINE_LAW):
    """Typical GB bill (old TDCVs) and each fuel's change vs April-June 2026."""
    q = year_quarters(year, "GB", law)
    out = {"bill": typical_bill(q, profile, TDCV_ELEC_KWH, TDCV_GAS_KWH)}
    for f, kwh in (("elec", TDCV_ELEC_KWH), ("gas", TDCV_GAS_KWH)):
        new = fuel_bill_for_profile(kwh, True, q[f], f, profile)
        old = fuel_bill_for_profile(kwh, True, HELD_QUARTERS[f], f, profile)
        out[f"{f}_pct"] = float(new / old - 1)
    return out


def household_bills(
    year, kwh, connected, is_ni, profile=CONSUMPTION_PROFILE, law=BASELINE_LAW
):
    """Bills per fuel under a VAT law. ``kwh``/``connected`` map fuel -> arrays."""
    gb_q, ni_q = _quarters(year, False, law), _quarters(year, True, law)
    out = {}
    for f in FUELS:
        gb = fuel_bill_for_profile(kwh[f], connected[f], gb_q[f], f, profile)
        ni = fuel_bill_for_profile(kwh[f], connected[f], ni_q[f], f, profile)
        out[f] = np.where(is_ni, ni, gb)
    return out


def held_bills(kwh, connected):
    """Bills at April-June 2026 tariffs (the cap-freeze level)."""
    return {
        f: fuel_bill_for_profile(kwh[f], connected[f], HELD_QUARTERS[f], f, "equal")
        for f in FUELS
    }


def cap_freeze_support(forecast, held):
    """Subsidy holding unit rates and standing charges at April-June 2026."""
    return np.maximum(
        forecast["elec"] + forecast["gas"] - held["elec"] - held["gas"], 0.0
    )


def vat_saving(year, kwh, connected, is_ni, profile, law_from, law_to):
    """Fall in each household's electricity bill moving from one VAT law to another."""
    a = household_bills(year, kwh, connected, is_ni, profile, law_from)["elec"]
    b = household_bills(year, kwh, connected, is_ni, profile, law_to)["elec"]
    return a - b


def levy_share(profile=CONSUMPTION_PROFILE):
    """Share of the typical 2027-28 GB electricity bill that £120 of levies is."""
    typical_elec = fuel_bill_for_profile(
        NEW_TDCV["elec"], True, year_quarters(2027)["elec"], "elec", profile
    )
    return LEVY_SAVING_TYPICAL / float(typical_elec)


def analytic_supports(
    year, forecast, held, kwh, connected, is_ni, profile=CONSUMPTION_PROFILE
):
    """Supports for the options costed directly from bills."""
    gb = ~is_ni
    out = {"cap_freeze": cap_freeze_support(forecast, held)}
    if year == 2027:
        out["extend_vat_cut"] = vat_saving(
            year, kwh, connected, is_ni, profile, BASELINE_LAW, "extend_2027_28"
        )
        out["remove_levies"] = np.where(gb, forecast["elec"] * levy_share(profile), 0.0)
    return out


YEARS = {
    2026: {"label": "2026-27"},
    2027: {"label": "2027-28"},
}


def _policies(year):
    period = f"{year}-01-01.{year}-12-31"
    from energy_budget.reforms.targeted_energy_discount.presets import PRESETS
    from energy_budget.reforms.targeted_energy_discount.reform import scenario

    return {
        "rf_targeted_discount": {
            "label": (
                "Targeted discount (RF, simplified): a flat £175 to GB households on "
                "means-tested benefits or whose highest individual income is under £24,000"
            ),
            "scenario": scenario(PRESETS["rf_flat"]),
            "assumptions": RF_ASSUMPTIONS,
            "note": (
                "Simplified fixed-payment illustration of the Resolution Foundation's "
                "unit-rate discount. Counted as HBAI income by assumption, by analogy "
                "with DWP's treatment of the Warm Home Discount."
            ),
            "links": [RF_LINK],
        },
        "whd_top_up": {
            # Reported Treasury plan: £150 to £250, taxpayer-funded, about
            # £600m for 6m households (FT, 11 Oct 2026; Guardian, 6 Oct 2026).
            "label": (
                f"Warm Home Discount top-up: an extra £{WHD_TOP_UP} to households that "
                "receive the rebate under the scheme's rules (England and Wales "
                "qualifying benefits, Scotland's core group), paid from taxation"
            ),
            "scenario": scenario(whd_top_up_changes(year)),
            "links": [*WHD_LINKS, WHD_IA_LINK],
        },
        "cost_of_living_payment": {
            "label": "£300 Cost of Living Payment to households on means-tested benefits",
            "params": {
                "gov.treasury.cost_of_living_support.means_tested_households.amount": {
                    period: 300
                }
            },
        },
        "flat_400": {
            "label": "£400 to every household (2022 EBSS design)",
            "params": {
                "gov.treasury.energy_bills_rebate.energy_bills_credit": {period: 400}
            },
        },
    }


@functools.cache
def whd_scheme(year):
    """The Warm Home Discount's rules for a scheme year, from policyengine-uk.

    Read at 1 April of the scheme year (the eligibility statement's start):
    the England and Wales qualifying benefits, the rebate and DESNZ's receipt
    rates. The model calculates no Scottish scheme.
    """
    from policyengine_uk import CountryTaxBenefitSystem

    p = CountryTaxBenefitSystem().parameters.gov.ofgem.warm_home_discount
    at = f"{year}-04-01"
    return {
        "qualifying_benefits": list(p.qualifying_benefits(at)),
        "rebate": float(p.amount(at)),
        "receipt_rate_pension_credit": float(p.receipt_rate.pension_credit(at)),
        "receipt_rate_other": float(p.receipt_rate.other_benefits(at)),
    }


def whd_top_up_changes(year):
    """Reform changes for the top-up: the scheme's eligibility and receipt rates."""
    from energy_budget.reforms.targeted_energy_discount.presets import PRESETS

    tp = "gov.contrib.targeted_energy_discount"
    rules = whd_scheme(year)
    return {
        **PRESETS["passport_only"],
        f"{tp}.amount[0].amount": WHD_TOP_UP,
        f"{tp}.amount[1].amount": WHD_TOP_UP,
        f"{tp}.passport.benefits": rules["qualifying_benefits"],
        f"{tp}.passport.scotland_core_group_only": True,
        f"{tp}.receipt_rate.pension_credit": rules["receipt_rate_pension_credit"],
        f"{tp}.receipt_rate.other_benefits": rules["receipt_rate_other"],
    }


def whd_sensitivities(w, eligible, pc, draw, scotland, scotland_list, rules):
    """Caseload and take-up sensitivities for the top-up, in households and £bn.

    ``eligible`` is the central eligibility (England and Wales qualifying
    benefits, Scotland's core group); ``scotland_list`` marks Scottish
    households on a qualifying benefit, for the broader-group variant.
    Expected values use the rates directly; drawn values use the seeded draw.
    """
    rate_pc = rules["receipt_rate_pension_credit"]
    rate_other = rules["receipt_rate_other"]

    def row(label, recipients):
        m = float(np.sum(recipients * w)) / 1e6
        return {
            "label": label,
            "recipients_m": round(m, 2),
            "cost_bn": round(m * WHD_TOP_UP / 1e3, 2),
        }

    def expected(elig, other=rate_other):
        return elig * np.where(pc, rate_pc, other)

    def drawn(elig, other=rate_other):
        return elig & (draw < np.where(pc, rate_pc, other))

    rows = [
        row("Every eligible household receives it", eligible.astype(float)),
        row(
            f"Receipt rates ({rate_pc:.0%} Pension Credit, {rate_other:.0%} other), "
            "expected value",
            expected(eligible),
        ),
        row("Receipt rates, seeded draw (central)", drawn(eligible)),
    ]
    for other in WHD_OTHER_RATE_SENSITIVITIES:
        rows.append(
            row(
                f"Other-benefits receipt rate {other:.0%} (impact assessment "
                "sensitivity), expected value",
                expected(eligible, other),
            )
        )
    rows += [
        row("England and Wales only (no Scottish top-up)", drawn(eligible & ~scotland)),
        row(
            "Scotland: every household on a qualifying benefit, as if the broader "
            "group were paid like the core group",
            drawn(eligible | (scotland & scotland_list)),
        ),
    ]
    rows.append(
        {
            "label": (
                f"Caseload set to DESNZ's estimate of about "
                f"{WHD_OFFICIAL_HOUSEHOLDS_M:.0f}m recipient households"
            ),
            "recipients_m": WHD_OFFICIAL_HOUSEHOLDS_M,
            "cost_bn": round(WHD_OFFICIAL_HOUSEHOLDS_M * WHD_TOP_UP / 1e3, 2),
        }
    )
    return rows


def _whd_note(o, rules):
    benefits = {
        "pension_credit": "Pension Credit",
        "universal_credit": "Universal Credit",
        "housing_benefit": "Housing Benefit",
        "esa_income": "income-related ESA",
        "jsa_income": "income-based JSA",
        "income_support": "Income Support",
    }
    listed = ", ".join(benefits.get(b, b) for b in rules["qualifying_benefits"])
    return (
        f"Eligible ({o['eligible_m']:.1f}m households): in England and Wales, "
        f"households where anyone receives {listed} (the scheme year's "
        "eligibility statement); in Scotland, the core group that receives the "
        "rebate without applying. Not every eligible household receives the "
        "rebate: the claimant or partner must be named on a participating "
        "supplier's electricity account and matched to DWP records. DESNZ's "
        "receipt rates are applied by policyengine-uk's seeded draw per household: "
        f"{rules['receipt_rate_pension_credit']:.0%} of households with Pension "
        f"Credit and {rules['receipt_rate_other']:.0%} of other eligible households "
        f"({o['recipients_m']:.1f}m recipients, against about "
        f"{WHD_OFFICIAL_HOUSEHOLDS_M:.0f}m in DESNZ's estimate for winter 2025/26)."
    )


ANALYTIC_OPTIONS = {
    "cap_freeze": {
        "label": (
            "Cap freeze: electricity and gas unit rates and standing charges held at "
            f"April–June 2026 levels (£{CURRENT_CAP:,} typical bill)"
        ),
        "note": (
            "Price restoration, not a payment: each household's forecast bill minus its "
            "bill at April–June 2026 tariffs for the same kWh (seasonal profile), floored "
            "at zero. Outside HBAI income, so no poverty effect. UK-wide, with Northern "
            "Ireland on GB prices as a proxy."
        ),
    },
    "extend_vat_cut": {
        "label": (
            "Keep 0% VAT on domestic electricity from July 2027 to March 2028, beyond "
            "the Budget's extension to June 2027 (UK-wide)"
        ),
        "note": (
            "Additional relief only: the Budget's zero rate to 30 June 2027 is already "
            "in the baseline. " + NOT_HBAI
        ),
    },
    "remove_levies": {
        "label": (
            f"Move remaining levies to taxation: £{LEVY_SAVING_TYPICAL} off a typical "
            "electricity bill, as a share of each GB electricity bill"
        ),
        "note": NOT_HBAI,
    },
}

OPTION_ORDER = [
    "rf_targeted_discount",
    "whd_top_up",
    "cost_of_living_payment",
    "flat_400",
    "cap_freeze",
    "extend_vat_cut",
    "remove_levies",
]


def _arr(sim, var, year, **kw):
    s = sim.calculate(var, year, **kw)
    return np.asarray(s.values if hasattr(s, "values") else s)


def _sim(year, elec, gas, params=None, extra_scenario=None):
    """A managed simulation with each household's forecast bills loaded.

    The bills (VAT included at each quarter's rate) replace the dataset's
    spending for ``year``. They feed only policyengine-uk's own energy VAT,
    which reaches household income solely through ``vat_change``; no
    simulation here changes a VAT rate, so that is zero (``_vat_change_gbp``).
    """
    sim = _build_simulation(reform=params or None, scenario=extra_scenario)
    sim.set_input("electricity_consumption", year, elec)
    sim.set_input("gas_consumption", year, gas)
    sim.set_input("domestic_energy_consumption", year, elec + gas)
    return sim


def _vat_change_gbp(sim, year, w):
    """Weighted sum of |vat_change|: must be zero (no VAT enters twice)."""
    return float(np.sum(np.abs(_arr(sim, "vat_change", year)) * w))


def _poverty(sim, year):
    """Person-weighted poverty rates (%).

    The main keys are relative poverty (below 60% of the median, the DWP HBAI
    headline measure, ``in_relative_poverty_*``). ``absolute_*`` keys are
    PolicyEngine UK's ``in_poverty_*``, which is absolute poverty against a
    fixed FYE 2025 line. ``child_*`` keys are under-18 rates (``age < 18``),
    not DWP's HBAI dependent-child cohort.
    """
    age = sim.calculate("age", year, map_to="person")
    out = {}
    for m in ("bhc", "ahc"):
        for prefix, var in (
            ("", f"in_relative_poverty_{m}"),
            ("absolute_", f"in_poverty_{m}"),
        ):
            pov = sim.calculate(var, year, map_to="person")
            out[f"{prefix}{m}"] = round(float(pov.mean()) * 100, 2)
            out[f"{prefix}child_{m}"] = round(float(pov[age < 18].mean()) * 100, 2)
    return out


def _poverty_change(after, before):
    return {k: round(after[k] - before[k], 2) for k in after}


def _bn(values, w):
    return round(float(np.sum(values * w)) / 1e9, 2)


def _sensitivity(year, kwh, connected, is_ni, w, profile):
    """Headline bills and analytic option costs under another profile."""
    fc = household_bills(year, kwh, connected, is_ni, profile)
    held = held_bills(kwh, connected)
    hit = fc["elec"] + fc["gas"] - held["elec"] - held["gas"]
    vat = vat_saving(
        year, kwh, connected, is_ni, profile, COUNTERFACTUAL_LAW, BASELINE_LAW
    )
    return {
        "typical_bill_old_tdcv": round(typical(year, profile)["bill"], 2),
        "mean_bill": round(weighted_mean(fc["elec"] + fc["gas"], w)),
        "mean_extra_cost": round(weighted_mean(hit, w)),
        "total_extra_cost_bn": _bn(hit, w),
        "budget_vat_extension_bn": _bn(vat, w),
        "option_cost_bn": {
            k: _bn(v, w)
            for k, v in analytic_supports(
                year, fc, held, kwh, connected, is_ni, profile
            ).items()
        },
    }


def _pre_budget_option_costs(year, cf, held, kwh, connected, is_ni, w):
    """Bill-costed option costs against pre-Budget bills.

    ``extend_vat_cut_previous_design`` is the option as previously published:
    0% VAT on GB electricity for the whole of 2027-28, against 5% law.
    """
    out = {"cap_freeze": _bn(cap_freeze_support(cf, held), w)}
    if year == 2027:
        gb = ~is_ni
        whole_year = vat_saving(
            year,
            kwh,
            connected,
            is_ni,
            CONSUMPTION_PROFILE,
            COUNTERFACTUAL_LAW,
            "no_vat",
        )
        out["extend_vat_cut_previous_design"] = _bn(np.where(gb, whole_year, 0.0), w)
        out["remove_levies"] = _bn(np.where(gb, cf["elec"] * levy_share(), 0.0), w)
    return out


def _hep_checks(sim, year, w, hep, gains):
    """The payment reaches only English bands A-D and enters income once.

    ``gains`` maps an income variable to baseline minus counterfactual.
    Benefits must rise by exactly the payment. Household net income does
    too, up to float32 rounding on very large incomes. HBAI income resets
    negative incomes to zero, so households that stay at or below zero gain
    less; the check uses the figure before that reset.
    """
    band = pd.Series(_arr(sim, "council_tax_band", year)).astype(str).to_numpy()
    country = pd.Series(_arr(sim, "country", year)).astype(str).to_numpy()
    eligible = (country == "ENGLAND") & np.isin(band, ["A", "B", "C", "D"])
    off = {k: np.abs(v - hep) for k, v in gains.items()}
    out = {
        "paid_outside_england_bands_a_to_d": int(np.sum((hep > 0) & ~eligible)),
        # Meaningful only in a year the payment is made.
        "eligible_not_paid": int(np.sum((hep == 0) & eligible))
        if np.any(hep)
        else None,
        "amounts_paid": sorted({float(x) for x in np.unique(hep[hep > 0])}),
        "recipients_m": round(float(np.sum((hep > 0) * w)) / 1e6, 2),
        "cost_bn": _bn(hep, w),
        **{f"{k}_gain_bn": _bn(v, w) for k, v in gains.items()},
        **{
            f"{k}_max_abs_gain_minus_payment": round(float(v.max()), 2)
            for k, v in off.items()
        },
        **{f"{k}_records_gain_differs": int(np.sum(v > 0.01)) for k, v in off.items()},
        "note": (
            "Benefits and HBAI income before the reset to zero rise by exactly the "
            "payment. HBAI income after the reset gains less for households that stay "
            "at or below zero. Household net income differs by a few pounds on a "
            "handful of very high-income records through float32 rounding; the "
            "weighted total of that difference is shown in pounds."
        ),
        "net_income_gain_minus_payment_total_gbp": round(
            float(np.sum((gains["household_net_income"] - hep) * w)), 2
        ),
    }
    if year == 2026 and (
        out["paid_outside_england_bands_a_to_d"]
        or out["eligible_not_paid"]
        or out["household_benefits_max_abs_gain_minus_payment"] > 0.01
        or out[
            "hbai_household_net_income_before_reset_to_zero_max_abs_gain_minus_payment"
        ]
        > 0.01
        or abs(out["net_income_gain_minus_payment_total_gbp"]) > 1e4
    ):
        raise AssertionError(f"Household Energy Payment check failed: {out}")
    return out


HEP_INCOME_VARS = [
    "household_benefits",
    "household_net_income",
    "hbai_household_net_income_before_reset_to_zero",
    "hbai_household_net_income",
]


def _vat_reconciliation(sim, year, fc, kwh, connected, is_ni, w):
    """Electricity VAT in the dashboard's bills vs policyengine-uk's own.

    The dashboard prices each quarter at that quarter's VAT rate and weights
    quarters by seasonal use. policyengine-uk charges the fiscal-year average
    rate (day-weighted, fiscal year from 6 April) on the bill divided by 1.05
    (its input price basis). Only the dashboard's figure enters any result.
    """
    ex = household_bills(year, kwh, connected, is_ni, CONSUMPTION_PROFILE, "no_vat")
    dashboard = fc["elec"] - ex["elec"]
    native_total = _arr(sim, "domestic_energy_vat", year)
    native_elec = native_total - fc["gas"] * VAT / (1 + VAT)
    return {
        "dashboard_elec_vat_bn": _bn(dashboard, w),
        "policyengine_uk_elec_vat_bn": _bn(native_elec, w),
        "dashboard_gas_vat_bn": _bn(fc["gas"] * VAT / (1 + VAT), w),
        "note": (
            "Dashboard: each quarter's rate on that quarter's seasonal share of use. "
            "policyengine-uk: fiscal-year day-weighted rate on bill / 1.05. Only the "
            "dashboard's figure enters results; the model's never reaches income "
            "because vat_change is zero."
        ),
    }


def _whd_details(ref, base, year, w, support, region_arr):
    """Caseload, sensitivities and the check against the model's own rebate."""
    rules = whd_scheme(year)
    eligible = _arr(ref, "targeted_energy_discount_eligible", year)
    pc = _arr(ref, "pension_credit", year, map_to="household") > 0
    draw = _arr(ref, "warm_home_discount_random_draw", year)
    scotland = region_arr == "SCOTLAND"
    scotland_list = (
        sum(
            _arr(ref, b, year, map_to="household") for b in rules["qualifying_benefits"]
        )
        > 0
    )
    core = _arr(ref, "targeted_energy_discount_scotland_core_group", year)
    rate = np.where(
        pc, rules["receipt_rate_pension_credit"], rules["receipt_rate_other"]
    )
    # The top-up should reach exactly the households the model gives the
    # £150 rebate in England and Wales: same benefits, rates and draw.
    rebate = _arr(base, "warm_home_discount", year)
    ew = ~scotland & (region_arr != "NORTHERN_IRELAND")
    differ = ew & ((support > 0) != (rebate > 0))
    return {
        "eligible_m": round(float(np.sum(eligible * w)) / 1e6, 2),
        "eligible_pension_credit_m": round(float(np.sum((eligible & pc) * w)) / 1e6, 2),
        "eligible_scotland_core_group_m": round(
            float(np.sum((eligible & scotland) * w)) / 1e6, 2
        ),
        "scotland_on_qualifying_benefit_m": round(
            float(np.sum((scotland & scotland_list) * w)) / 1e6, 2
        ),
        "scotland_core_group_records": int(np.sum(scotland & core)),
        "expected_recipients_m": round(float(np.sum(eligible * rate * w)) / 1e6, 2),
        "scheme_rules": rules,
        "sensitivities": whd_sensitivities(
            w, eligible, pc, draw, scotland, scotland_list, rules
        ),
        "check_against_model_rebate": {
            "england_wales_rebate_recipients_m": round(
                float(np.sum((ew & (rebate > 0)) * w)) / 1e6, 2
            ),
            "england_wales_top_up_recipients_m": round(
                float(np.sum((ew & (support > 0)) * w)) / 1e6, 2
            ),
            "records_differ": int(np.sum(differ)),
            "households_differ_m": round(float(np.sum(differ * w)) / 1e6, 3),
        },
    }


def run_budget_options(data):
    """Score the Budget measures and every option against each year's baseline."""
    kwh = {"elec": data["elec_kwh"], "gas": data["gas_kwh"]}
    connected = {"elec": data["has_elec"], "gas": data["has_gas"]}
    held = {"elec": data["elec"], "gas": data["gas"]}
    region_all = pd.Series(data["region"]).astype(str).to_numpy()
    is_ni = region_all == "NORTHERN_IRELAND"
    alt_profile = "equal" if CONSUMPTION_PROFILE == "seasonal" else "seasonal"

    results = {}
    for year, y in YEARS.items():
        fc = household_bills(year, kwh, connected, is_ni)
        cf = household_bills(year, kwh, connected, is_ni, law=COUNTERFACTUAL_LAW)
        elec, gas = fc["elec"], fc["gas"]
        hit = elec + gas - held["elec"] - held["gas"]
        cf_hit = cf["elec"] + cf["gas"] - held["elec"] - held["gas"]
        typ = typical(year)
        typ_cf = typical(year, law=COUNTERFACTUAL_LAW)

        base = _sim(year, elec, gas)
        w = _arr(base, "household_weight", year, unweighted=True)
        base_net = _arr(base, "household_net_income", year)
        hep = _arr(base, "household_energy_payment", year)
        decile = _arr(base, "household_income_decile", year)
        base_poverty = _poverty(base, year)
        vat_change = {"baseline": _vat_change_gbp(base, year, w)}
        vat_rec = _vat_reconciliation(base, year, fc, kwh, connected, is_ni, w)
        hh_type = data["hh_type"]
        types = [t for t in sorted(set(hh_type)) if t != "OTHER"]

        def by_type(values, w=w, hh_type=hh_type, types=types):
            return {t: round(weighted_mean(values, w, hh_type == t)) for t in types}

        region_arr = pd.Series(_arr(base, "region", year)).astype(str).to_numpy()
        if not (region_arr == region_all).all():
            raise ValueError("household order changed between simulations")
        regions = [r for r in sorted(set(region_arr)) if r not in ("", "UNKNOWN")]

        def by_region(values, w=w, region_arr=region_arr, regions=regions):
            return {
                r: round(weighted_mean(values, w, region_arr == r)) for r in regions
            }

        def summarise(
            label,
            support,
            poverty=None,
            note=None,
            w=w,
            hit=hit,
            decile=decile,
            **extra,
        ):
            pos_hit = np.maximum(hit, 0)
            recipients_m = float(np.sum((support > 0) * w)) / 1e6
            return {
                "label": label,
                "cost_bn": _bn(support, w),
                "avg_per_household": round(weighted_mean(support, w)),
                "share_receiving_pct": round(
                    float(np.sum((support > 0) * w) / np.sum(w)) * 100, 1
                ),
                "recipients_m": round(recipients_m, 2),
                "share_of_shock_offset_pct": round(
                    float(
                        np.sum(np.minimum(support, pos_hit) * w) / np.sum(pos_hit * w)
                    )
                    * 100,
                    1,
                ),
                "deciles": [
                    round(weighted_mean(support, w, decile == d)) for d in range(1, 11)
                ],
                "by_hh_type": by_type(support),
                "by_region": by_region(support),
                "poverty": poverty,
                "note": note,
                **extra,
            }

        # ── The Budget's energy measures, against the counterfactual ──
        base_income = {v: _arr(base, v, year) for v in HEP_INCOME_VARS}
        if np.any(hep != 0):
            period = f"{year}-01-01.{year}-12-31"
            cf_sim = _sim(year, cf["elec"], cf["gas"], {HEP_PARAMETER: {period: 0}})
            if np.any(_arr(cf_sim, "household_energy_payment", year) != 0):
                raise AssertionError(
                    "counterfactual still pays the Household Energy Payment"
                )
            cf_income = {v: _arr(cf_sim, v, year) for v in HEP_INCOME_VARS}
            cf_poverty = _poverty(cf_sim, year)
            vat_change["counterfactual"] = _vat_change_gbp(cf_sim, year, w)
            del cf_sim
            gc.collect()
        else:
            # No payment this year, so the counterfactual's income is the
            # baseline's; only bills differ.
            cf_income, cf_poverty = base_income, base_poverty
        gains = {v: base_income[v] - cf_income[v] for v in HEP_INCOME_VARS}
        hep_gain = gains["household_net_income"]
        hep_check = _hep_checks(base, year, w, hep, gains)
        vat_ext = vat_saving(
            year,
            kwh,
            connected,
            is_ni,
            CONSUMPTION_PROFILE,
            COUNTERFACTUAL_LAW,
            BASELINE_LAW,
        )
        measures = {
            "household_energy_payment": summarise(
                "£100 Household Energy Payment (England, council tax bands A–D)",
                hep_gain,
                hit=cf_hit,
                poverty_change_pp=_poverty_change(base_poverty, cf_poverty),
                counted_in_hbai_income=True,
            ),
            "electricity_vat_extension": summarise(
                "0% VAT on domestic electricity extended to 30 June 2027 (UK-wide from April 2027)",
                vat_ext,
                hit=cf_hit,
                poverty_change_pp=None,
                counted_in_hbai_income=False,
            ),
        }
        measures["combined"] = summarise(
            "Both Budget energy measures",
            hep_gain + vat_ext,
            hit=cf_hit,
            poverty_change_pp=_poverty_change(base_poverty, cf_poverty),
        )

        # ── Further options, against the post-Budget baseline ──
        rows = {}
        for key, p in _policies(year).items():
            ref = _sim(year, elec, gas, p.get("params"), p.get("scenario"))
            support = _arr(ref, "household_net_income", year) - base_net
            vat_change[key] = _vat_change_gbp(ref, year, w)
            rows[key] = summarise(
                p["label"],
                support,
                _poverty(ref, year),
                p.get("note"),
                assumptions=p.get("assumptions"),
                links=p.get("links"),
            )
            if key == "whd_top_up":
                rows[key].update(_whd_details(ref, base, year, w, support, region_arr))
            del ref
            gc.collect()
        whd = rows["whd_top_up"]
        whd["note"] = _whd_note(whd, whd_scheme(year))

        for key, support in analytic_supports(
            year, fc, held, kwh, connected, is_ni
        ).items():
            meta = ANALYTIC_OPTIONS[key]
            rows[key] = summarise(meta["label"], support, note=meta["note"])
            if key == "remove_levies":
                rows[key]["bill_cut_pct"] = round(levy_share() * 100, 1)
        rows = {k: rows[k] for k in OPTION_ORDER if k in rows}

        if max(vat_change.values()) > 1.0:
            raise AssertionError(f"policyengine-uk VAT reached income: {vat_change}")

        zero_kwh = {
            f: round(
                float(np.sum(w * (connected[f] & (kwh[f] == 0))) / np.sum(w)) * 100, 2
            )
            for f in FUELS
        }
        results[y["label"]] = {
            "baseline": {
                "policy": BASELINE_LAW,
                "consumption_profile": CONSUMPTION_PROFILE,
                "elec_price_vs_apr_jun_2026_pct": round(typ["elec_pct"] * 100, 1),
                "gas_price_vs_apr_jun_2026_pct": round(typ["gas_pct"] * 100, 1),
                "typical_bill_old_tdcv": round(typ["bill"]),
                "typical_bill_old_tdcv_exact": round(typ["bill"], 2),
                "total_bill_dataset_prices_bn": _bn(
                    data["elec_spend"] + data["gas_spend"], w
                ),
                "implied_twh": {
                    "elec": round(float(np.sum(kwh["elec"] * w)) / 1e9, 1),
                    "gas": round(float(np.sum(kwh["gas"] * w)) / 1e9, 1),
                },
                # Connected households with zero use of a fuel: only the
                # standing charge moves for them.
                "connected_zero_kwh_pct": zero_kwh,
                "households_m": round(float(np.sum(w)) / 1e6, 2),
                "mean_bill": round(weighted_mean(elec + gas, w)),
                "mean_bill_apr_jun_2026_prices": round(
                    weighted_mean(held["elec"] + held["gas"], w)
                ),
                "total_bill_bn": _bn(elec + gas, w),
                "bill_by_decile": [
                    round(weighted_mean(elec + gas, w, decile == d))
                    for d in range(1, 11)
                ],
                "bill_by_hh_type": by_type(elec + gas),
                "bill_by_region": by_region(elec + gas),
                "mean_extra_cost": round(weighted_mean(hit, w)),
                "total_extra_cost_bn": _bn(hit, w),
                "extra_cost_by_hh_type": by_type(hit),
                "extra_cost_by_region": by_region(hit),
                "income_by_decile": [
                    round(weighted_mean(base_net, w, decile == d)) for d in range(1, 11)
                ],
                "extra_cost_by_decile": [
                    round(weighted_mean(hit, w, decile == d)) for d in range(1, 11)
                ],
                "hh_type_share_pct": {
                    t: round(float(np.sum(w * (hh_type == t)) / np.sum(w)) * 100, 1)
                    for t in sorted(set(hh_type))
                },
                "poverty": base_poverty,
                "note": TARIFF_NOTE,
                "note_link": TARIFF_NOTE_LINK,
                "sensitivities": {
                    f"profile_{alt_profile}": _sensitivity(
                        year, kwh, connected, is_ni, w, alt_profile
                    ),
                },
            },
            "pre_budget": {
                "description": BUDGET_COUNTERFACTUAL,
                "typical_bill_old_tdcv": round(typ_cf["bill"]),
                "typical_bill_old_tdcv_exact": round(typ_cf["bill"], 2),
                "mean_bill": round(weighted_mean(cf["elec"] + cf["gas"], w)),
                "total_bill_bn": _bn(cf["elec"] + cf["gas"], w),
                "mean_extra_cost": round(weighted_mean(cf_hit, w)),
                "total_extra_cost_bn": _bn(cf_hit, w),
                "poverty": cf_poverty,
                # The bill-costed options as previously defined, on pre-Budget
                # bills: used to split changes into policy and data effects.
                "option_cost_bn": _pre_budget_option_costs(
                    year, cf, held, kwh, connected, is_ni, w
                ),
            },
            "budget_measures": measures,
            "options": rows,
            "validation": {
                "household_energy_payment": hep_check,
                "vat_change_abs_gbp_by_simulation": {
                    k: round(v, 2) for k, v in vat_change.items()
                },
                "vat_reconciliation": vat_rec,
            },
        }
        del base
        gc.collect()
    return results
