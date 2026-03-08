import { useQuery } from "@tanstack/react-query";
import { fetchCostFromDb } from "@/lib/api";
import { Granularity } from "@/lib/types";

/**
 * Fetches cost data from the local database via GET /cost/db.
 *
 * Date resolution (mirrors backend logic):
 *   - granularity=daily,   no dates → backend uses last ALERT_HISTORY_DAYS days
 *   - granularity=monthly, no dates → backend uses last ALERT_HISTORY_MONTHS * 30 days
 *   - any explicit dates            → passed through as-is
 *
 * Caching layers:
 *   1. React Query staleTime (60 s) — zero network requests within one minute
 *   2. Backend TTL cache (5 min daily / 30 min monthly) — no DB query on repeat calls
 */
export function useCostData(
  granularity: Granularity,
  startDate?: string,
  endDate?: string,
) {
  return useQuery({
    // Include all three params in the key so React Query caches each unique
    // combination separately and re-fetches automatically when any changes.
    queryKey: ["cost-data", granularity, startDate ?? "", endDate ?? ""],
    queryFn: () => fetchCostFromDb(granularity, startDate, endDate),
    retry: 1,
    staleTime: 60_000, // 60 seconds — layer-1 cache in the browser
  });
}
