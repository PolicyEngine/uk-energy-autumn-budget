/**
 * Shared policy selection across the Budget responses and Household effects tabs.
 *
 * The dashboard keeps one *requested* option id (what the user last clicked) and resolves it against
 * the financial year on every render. If the requested option has no result in that year, the charts
 * and the detail panel fall back together to the first option that does, and `isFallback` tells the
 * UI to say so. The request itself is kept, so switching back to a year that has it restores it.
 */

/** Option ids with a result in `fy`, in the order they appear in `optionRows`. */
export function availableOptionIds(optionRows, fy) {
  return optionRows.filter((r) => r.fy === fy).map((r) => r.option_id);
}

/** Financial years in which `optionId` has a result, in data order. */
export function yearsForOption(optionRows, optionId) {
  const years = [];
  for (const r of optionRows) {
    if (r.option_id === optionId && !years.includes(r.fy)) years.push(r.fy);
  }
  return years;
}

/**
 * Resolve the requested option for a financial year.
 *
 * @returns {{ id: string|null, requestedId: string, isFallback: boolean, availableIds: string[],
 *   requestedYears: string[] }}
 *   `id` is the option every chart and panel should show; `requestedYears` lists the years in which
 *   the requested option does have a result (for the explanatory note).
 */
export function resolvePolicySelection(requestedId, fy, optionRows) {
  const availableIds = availableOptionIds(optionRows, fy);
  const requestedYears = yearsForOption(optionRows, requestedId);
  if (availableIds.includes(requestedId)) {
    return { id: requestedId, requestedId, isFallback: false, availableIds, requestedYears };
  }
  return {
    id: availableIds[0] ?? null,
    requestedId,
    isFallback: true,
    availableIds,
    requestedYears,
  };
}
