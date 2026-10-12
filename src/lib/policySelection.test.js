import { describe, expect, test } from "bun:test";
import { availableOptionIds, resolvePolicySelection, yearsForOption } from "./policySelection.js";
import options from "../data/options.json";

const ROWS = [
  { fy: "2026-27", option_id: "rf_targeted_discount" },
  { fy: "2026-27", option_id: "cap_freeze" },
  { fy: "2027-28", option_id: "rf_targeted_discount" },
  { fy: "2027-28", option_id: "cap_freeze" },
  { fy: "2027-28", option_id: "remove_levies" },
  { fy: "2027-28", option_id: "extend_vat_cut" },
];

describe("resolvePolicySelection", () => {
  test("one selection drives both tabs: the same request resolves to the same option", () => {
    // Budget tab and Household tab both resolve the single shared request.
    const budget = resolvePolicySelection("cap_freeze", "2027-28", ROWS);
    const households = resolvePolicySelection("cap_freeze", "2027-28", ROWS);
    expect(budget.id).toBe("cap_freeze");
    expect(households.id).toBe(budget.id);
    expect(budget.isFallback).toBe(false);
  });

  test("an option available in both years survives a year switch", () => {
    expect(resolvePolicySelection("cap_freeze", "2026-27", ROWS).id).toBe("cap_freeze");
    expect(resolvePolicySelection("cap_freeze", "2027-28", ROWS).id).toBe("cap_freeze");
  });

  test("switching to a year without the option falls back explicitly", () => {
    const sel = resolvePolicySelection("remove_levies", "2026-27", ROWS);
    expect(sel.isFallback).toBe(true);
    expect(sel.requestedId).toBe("remove_levies");
    expect(sel.id).toBe("rf_targeted_discount");
    expect(sel.availableIds).not.toContain("remove_levies");
    expect(sel.requestedYears).toEqual(["2027-28"]);
  });

  test("the request is kept, so returning to its year restores it", () => {
    const back = resolvePolicySelection("remove_levies", "2027-28", ROWS);
    expect(back.id).toBe("remove_levies");
    expect(back.isFallback).toBe(false);
  });

  test("the resolved option always has a result in the selected year", () => {
    for (const fy of ["2026-27", "2027-28"]) {
      for (const { option_id } of ROWS) {
        const sel = resolvePolicySelection(option_id, fy, ROWS);
        expect(availableOptionIds(ROWS, fy)).toContain(sel.id);
      }
    }
  });

  test("an unknown request falls back rather than leaving the charts empty", () => {
    const sel = resolvePolicySelection("not_an_option", "2027-28", ROWS);
    expect(sel.isFallback).toBe(true);
    expect(sel.id).toBe("rf_targeted_discount");
    expect(sel.requestedYears).toEqual([]);
  });

  test("a year with no options resolves to null", () => {
    expect(resolvePolicySelection("cap_freeze", "2030-31", ROWS).id).toBeNull();
  });
});

describe("helpers", () => {
  test("yearsForOption lists each year once", () => {
    expect(yearsForOption(ROWS, "cap_freeze")).toEqual(["2026-27", "2027-28"]);
    expect(yearsForOption(ROWS, "extend_vat_cut")).toEqual(["2027-28"]);
  });
});

describe("generated options.json", () => {
  // Properties that must hold however the model regenerates the data.
  test("every option resolves to one with a result in every year", () => {
    const years = [...new Set(options.map((o) => o.fy))];
    const ids = [...new Set(options.map((o) => o.option_id))];
    for (const fy of years) {
      for (const id of ids) {
        const sel = resolvePolicySelection(id, fy, options);
        expect(options.some((o) => o.fy === fy && o.option_id === sel.id)).toBe(true);
        expect(sel.isFallback).toBe(!options.some((o) => o.fy === fy && o.option_id === id));
      }
    }
  });
});
