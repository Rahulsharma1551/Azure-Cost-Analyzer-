import { CostResponse, AlertThreshold } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import {
  IndianRupee,
  Zap,
  Layers,
  CircleDollarSign,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";

interface StatCardsProps {
  data: CostResponse | undefined;
  budget: number;
  thresholds?: AlertThreshold[];
}

export function StatCards({ data, budget, thresholds = [] }: StatCardsProps) {
  const totalCost = data?.total_cost ?? 0;
  const records = data?.data ?? [];

  const serviceMap = new Map<string, number>();
  records.forEach((r) =>
    serviceMap.set(
      r.service_name,
      (serviceMap.get(r.service_name) ?? 0) + r.cost,
    ),
  );
  const topService = [...serviceMap.entries()].sort((a, b) => b[1] - a[1])[0];
  const activeServices = serviceMap.size;

  // If exactly one budget threshold is set, compare that service's cost to its budget.
  // Otherwise compare total cost to the sum of all budgets.
  const { budgetPct, budgetLabel } = (() => {
    if (budget === 0) return { budgetPct: 0, budgetLabel: "Not set" };
    if (thresholds.length === 1) {
      const t = thresholds[0];
      const svcCost = serviceMap.get(t.service_name) ?? 0;
      const svcBudget = t.absolute_threshold ?? 0;
      if (svcBudget === 0) return { budgetPct: 0, budgetLabel: "Not set" };
      const pct = Math.round((svcCost / svcBudget) * 100);
      return { budgetPct: pct, budgetLabel: `${pct}% (${t.service_name})` };
    }
    const pct = Math.round((totalCost / budget) * 100);
    return { budgetPct: pct, budgetLabel: `${pct}%` };
  })();

  // Split records into two equal halves by date, compare totals to get real % change
  const pctChange = (() => {
    if (records.length < 2) return 0;
    const sorted = [...records].sort((a, b) => a.date.localeCompare(b.date));
    const mid = Math.floor(sorted.length / 2);
    const firstHalf = sorted.slice(0, mid).reduce((s, r) => s + r.cost, 0);
    const secondHalf = sorted.slice(mid).reduce((s, r) => s + r.cost, 0);
    if (firstHalf === 0) return 0;
    return Math.round(((secondHalf - firstHalf) / firstHalf) * 100);
  })();
  const isUp = pctChange > 0;

  const budgetBarColor =
    budgetPct > 100
      ? "bg-destructive"
      : budgetPct > 80
        ? "bg-warning"
        : "bg-primary";

  const stats = [
    {
      label: "Total Cost",
      value: `₹${totalCost.toLocaleString("en-IN", {
        maximumFractionDigits: 2,
      })}`,
      icon: IndianRupee,
      iconBg: "bg-primary/15 text-primary",
      badge:
        pctChange !== 0 ? (
          <span
            className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
              isUp
                ? "bg-destructive/15 text-destructive"
                : "bg-success/15 text-success"
            }`}
          >
            {isUp ? (
              <TrendingUp className="h-3 w-3" strokeWidth={1.5} />
            ) : (
              <TrendingDown className="h-3 w-3" strokeWidth={1.5} />
            )}
            {Math.abs(pctChange)}%
          </span>
        ) : null,
      extra: null,
    },
    {
      label: "Top Service",
      value: topService?.[0] ?? "—",
      icon: Zap,
      iconBg: "bg-success/15 text-success",
      badge: null,
      extra: null,
    },
    {
      label: "Active Services",
      value: String(activeServices),
      icon: Layers,
      iconBg: "bg-chart-4/15 text-chart-4",
      badge: null,
      extra: null,
    },
    {
      label: "Budget Used",
      value: budget > 0 ? budgetLabel : "Not set",
      icon: CircleDollarSign,
      iconBg: "bg-warning/15 text-warning",
      badge: null,
      extra:
        budget > 0 ? (
          <div className="mt-1.5 w-full">
            <Progress
              value={Math.min(budgetPct, 100)}
              className="h-1.5"
              indicatorClassName={budgetBarColor}
            />
          </div>
        ) : null,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((s) => (
        <Card
          key={s.label}
          className="border-border bg-card transition-shadow hover:shadow-md"
        >
          <CardContent className="flex items-center gap-4 p-4">
            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${s.iconBg}`}
            >
              <s.icon className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <div className="flex items-center gap-2">
                <p className="truncate text-lg font-semibold">{s.value}</p>
                {s.badge}
              </div>
              {s.extra}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
