import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FilterSettings } from "@/lib/types";
import { getAlertThresholds } from "@/lib/api";
import { useCostData } from "@/hooks/use-cost-data";
import { ControlPanel } from "@/components/dashboard/ControlPanel";
import { StatCards } from "@/components/dashboard/StatCards";
import { CostAreaChart } from "@/components/dashboard/CostAreaChart";
import { CostBarChart } from "@/components/dashboard/CostBarChart";
import { CostDonutChart } from "@/components/dashboard/CostDonutChart";
import { CostTable } from "@/components/dashboard/CostTable";
import { Skeleton } from "@/components/ui/skeleton";
import { WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

const Index = () => {
  const navigate = useNavigate();

  const [filters, setFilters] = useState<FilterSettings>({
    granularity: "daily",
    groupBy: "service",
    budget: 0,
    startDate: "",
    endDate: "",
  });

  const { data, isLoading, isError } = useCostData(
    filters.granularity,
    filters.startDate || undefined,
    filters.endDate || undefined,
  );

  const { data: thresholds = [] } = useQuery({
    queryKey: ["alert-thresholds"],
    queryFn: () => getAlertThresholds({ active_only: true }),
    staleTime: 60_000,
  });

  const totalBudget = useMemo(
    () =>
      thresholds
        .filter((t) => t.period_type === filters.granularity)
        .reduce((sum, t) => sum + (t.absolute_threshold ?? 0), 0),
    [thresholds, filters.granularity],
  );

  const handleApplyFilters = useCallback((f: FilterSettings) => {
    setFilters(f);
  }, []);

  const records = useMemo(() => {
    let items = data?.data ?? [];
    if (filters.startDate) {
      items = items.filter((r) => r.date.slice(0, 10) >= filters.startDate);
    }
    if (filters.endDate) {
      items = items.filter((r) => r.date.slice(0, 10) <= filters.endDate);
    }
    return items;
  }, [data, filters.startDate, filters.endDate]);

  return (
    <div className="min-h-full bg-background text-foreground">
      {/* Top bar */}
      <div className="flex items-center px-6 py-4">
        <h2 className="text-lg font-semibold">Dashboard</h2>
      </div>

      <div className="mx-auto max-w-7xl space-y-6 px-6 pb-6">
        <ControlPanel filters={filters} onApplyFilters={handleApplyFilters} />

        {isLoading && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-24 rounded-lg" />
              ))}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Skeleton className="h-[340px] rounded-lg" />
              <Skeleton className="h-[340px] rounded-lg" />
            </div>
            <Skeleton className="h-[320px] rounded-lg" />
            <Skeleton className="h-[400px] rounded-lg" />
          </div>
        )}

        {isError && !isLoading && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-destructive/40 py-16 text-center">
            <WifiOff className="h-10 w-10 text-destructive" strokeWidth={1.5} />
            <p className="text-sm text-destructive">
              Failed to fetch data. Ensure your FastAPI backend is running at
              the configured URL.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/settings")}
            >
              Check Settings
            </Button>
          </div>
        )}

        {data && !isLoading && (
          <>
            <StatCards
              data={data}
              budget={totalBudget}
              thresholds={thresholds.filter(
                (t) => t.period_type === filters.granularity,
              )}
            />
            <div className="grid gap-4 lg:grid-cols-2">
              <CostBarChart records={records} />
              <CostDonutChart records={records} budget={totalBudget} />
            </div>
            <CostAreaChart records={records} />
            <CostTable records={records} />
          </>
        )}
      </div>
    </div>
  );
};

export default Index;
