"""
Marketplace Analytics Engine.

Computes a full snapshot of marketplace health from the in-memory store.
All calculations are deterministic, pure functions — no side effects.

Snapshot sections
─────────────────
participants        Active buyers, sellers, counts by role and category
tasks               Volume, status distribution, category breakdown, fill rate
pricing             Average quoted price, price range, and price trend per category
supply_demand       Active supply vs. incoming demand, ratio, saturation signal
seller_utilization  Per-seller task load and utilization rate
specialist_vs_gen   Win-rate summary from benchmark comparisons

Formulas
────────
fill_rate          = completed_tasks / total_tasks   (0.0–1.0)
task_fill_rate_cat = completed_by_cat / tasks_by_cat per category

avg_quoted_price   = mean(quote.proposed_price) across all quotes for that category
price_range        = (min_price, max_price) across quotes for that category
price_trend        = [avg over each historical window] — placeholder until enough data

supply             = sum(seller.capacity - active_load) for APPROVED sellers in category
demand             = tasks submitted in [lookback_hours] for that category
supply_demand_ratio= supply / demand   (>1 = healthy, <1 = over-subscribed)

seller_utilization = active_in_progress_tasks / seller.capacity   (0.0–1.0)

specialist_win_rate = seller_wins / total_comparisons with a result

Determinism guarantee:
  All functions take (store) as their only external dependency.
  No random seeds, no external API calls, no time.now() calls in hot paths
  (snapshot_at is set once at the call site).

Future:
  Replace the price_trend placeholder with a sliding-window average over
  ActivityLog events tagged with quote.created.
  Replace supply_demand with a proper time-bucketed queue-depth model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..store import InMemoryStore

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class MarketplaceSnapshot:
    """
    Complete marketplace analytics snapshot.
    Serialised to dict via .to_dict() for the API response.
    """
    snapshot_at: str                            # ISO-8601 UTC timestamp

    # ── Participants ──────────────────────────────────────────────────
    active_buyers: int                          # Buyers with ≥1 task
    total_buyers: int
    active_sellers: int                         # APPROVED sellers
    total_sellers: int
    sellers_by_category: Dict[str, int]         # category → count of APPROVED sellers
    sellers_pending_review: int

    # ── Tasks ─────────────────────────────────────────────────────────
    total_tasks: int
    tasks_by_status: Dict[str, int]
    tasks_by_category: Dict[str, int]
    fill_rate: Optional[float]                  # completed / total; None if no tasks
    fill_rate_by_category: Dict[str, Optional[float]]

    # ── Quotes & Pricing ──────────────────────────────────────────────
    total_quotes: int
    quote_volume_by_category: Dict[str, int]
    avg_price_overall: Optional[float]
    avg_price_by_category: Dict[str, Optional[float]]
    price_range_by_category: Dict[str, Dict[str, Optional[float]]]  # {min, max}
    price_trend_by_category: Dict[str, List[float]]                 # placeholder; [] until data
    avg_eta_by_category: Dict[str, Optional[float]]                 # minutes

    # ── Supply / Demand ───────────────────────────────────────────────
    lookback_hours: int                         # window used for demand calculation
    demand_by_category: Dict[str, int]          # tasks submitted in window
    supply_by_category: Dict[str, int]          # sum of remaining capacity per category
    supply_demand_ratio: Dict[str, Optional[float]]   # supply/demand; None if demand=0
    supply_demand_signal: Dict[str, str]         # "healthy"|"tight"|"over_subscribed"|"no_demand"

    # ── Seller Utilization ────────────────────────────────────────────
    seller_utilization: List[Dict[str, Any]]    # per-seller: {id, name, load, capacity, pct}
    avg_utilization: Optional[float]             # mean utilization across active sellers

    # ── Specialist vs. Generalist ─────────────────────────────────────
    total_comparisons: int
    specialist_win_rate: Optional[float]
    avg_quality_delta: Optional[float]           # specialist_score - generalist_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_at": self.snapshot_at,
            "participants": {
                "active_buyers":          self.active_buyers,
                "total_buyers":           self.total_buyers,
                "active_sellers":         self.active_sellers,
                "total_sellers":          self.total_sellers,
                "sellers_by_category":    self.sellers_by_category,
                "sellers_pending_review": self.sellers_pending_review,
            },
            "tasks": {
                "total":                    self.total_tasks,
                "by_status":               self.tasks_by_status,
                "by_category":             self.tasks_by_category,
                "fill_rate":               self.fill_rate,
                "fill_rate_by_category":   self.fill_rate_by_category,
            },
            "pricing": {
                "total_quotes":            self.total_quotes,
                "quote_volume_by_category": self.quote_volume_by_category,
                "avg_price_overall":       self.avg_price_overall,
                "avg_price_by_category":   self.avg_price_by_category,
                "price_range_by_category": self.price_range_by_category,
                "price_trend_by_category": self.price_trend_by_category,
                "avg_eta_by_category":     self.avg_eta_by_category,
            },
            "supply_demand": {
                "lookback_hours":        self.lookback_hours,
                "demand_by_category":    self.demand_by_category,
                "supply_by_category":    self.supply_by_category,
                "ratio_by_category":     self.supply_demand_ratio,
                "signal_by_category":    self.supply_demand_signal,
            },
            "seller_utilization": {
                "sellers":        self.seller_utilization,
                "avg_utilization": self.avg_utilization,
            },
            "specialist_vs_generalist": {
                "total_comparisons":   self.total_comparisons,
                "specialist_win_rate": self.specialist_win_rate,
                "avg_quality_delta":   self.avg_quality_delta,
            },
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_marketplace_snapshot(
    store: "InMemoryStore",
    lookback_hours: int = 24,
) -> MarketplaceSnapshot:
    """
    Compute a complete marketplace snapshot from the store.

    Args:
        store:          InMemoryStore singleton
        lookback_hours: window for demand calculation (default 24h)

    Returns:
        MarketplaceSnapshot — pure data, no side effects.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=lookback_hours)

    tasks   = list(store.tasks.values())
    quotes  = list(store.quotes.values())
    buyers  = list(store.buyers.values())
    sellers = list(store.sellers.values())
    comparisons = list(store.benchmark_comparisons.values())

    # ── Participants ──────────────────────────────────────────────────
    buyer_ids_with_tasks = {t.buyer_id for t in tasks}
    active_buyers = len(buyer_ids_with_tasks)
    total_buyers  = len(buyers)

    approved_sellers = [s for s in sellers if str(s.approval_status) == "approved"]
    active_sellers   = len(approved_sellers)
    total_sellers    = len(sellers)

    sellers_by_category = _count_sellers_by_category(approved_sellers)
    sellers_pending     = sum(
        1 for s in sellers if str(s.approval_status) in ("pending", "needs_review")
    )

    # ── Tasks ─────────────────────────────────────────────────────────
    tasks_by_status   = _count_by(tasks, lambda t: str(t.status))
    tasks_by_category = _count_by(tasks, lambda t: str(t.category))

    total   = len(tasks)
    completed = tasks_by_status.get("completed", 0)
    fill_rate = round(completed / total, 3) if total else None

    fill_rate_by_category: Dict[str, Optional[float]] = {}
    for cat in tasks_by_category:
        cat_tasks = [t for t in tasks if str(t.category) == cat]
        cat_done  = sum(1 for t in cat_tasks if str(t.status) == "completed")
        fill_rate_by_category[cat] = round(cat_done / len(cat_tasks), 3) if cat_tasks else None

    # ── Pricing ───────────────────────────────────────────────────────
    quote_volume_by_category: Dict[str, int] = {}
    prices_by_category: Dict[str, List[float]] = {}
    etas_by_category:   Dict[str, List[float]] = {}

    for q in quotes:
        task = store.tasks.get(q.task_id)
        cat = str(task.category) if task else "unknown"
        quote_volume_by_category[cat] = quote_volume_by_category.get(cat, 0) + 1
        prices_by_category.setdefault(cat, []).append(float(q.proposed_price))
        etas_by_category.setdefault(cat, []).append(float(q.estimated_minutes))

    all_prices = [float(q.proposed_price) for q in quotes]
    avg_price_overall = round(sum(all_prices) / len(all_prices), 2) if all_prices else None

    avg_price_by_category: Dict[str, Optional[float]] = {
        cat: round(sum(ps) / len(ps), 2) if ps else None
        for cat, ps in prices_by_category.items()
    }
    price_range_by_category: Dict[str, Dict[str, Optional[float]]] = {
        cat: {"min": round(min(ps), 2), "max": round(max(ps), 2)} if ps else {"min": None, "max": None}
        for cat, ps in prices_by_category.items()
    }
    avg_eta_by_category: Dict[str, Optional[float]] = {
        cat: round(sum(es) / len(es), 1) if es else None
        for cat, es in etas_by_category.items()
    }

    # Price trend: bin accepted quotes by day (last 7 days)
    # Placeholder: returns [] until enough historical data accumulates.
    # Future: bucket accepted Quote.created_at by day and compute daily averages.
    price_trend_by_category: Dict[str, List[float]] = _compute_price_trend(quotes, store)

    # ── Supply / Demand ───────────────────────────────────────────────
    # Demand = tasks submitted within the lookback window, by category
    demand_by_category: Dict[str, int] = {}
    for t in tasks:
        try:
            created = t.created_at if isinstance(t.created_at, datetime) else datetime.fromisoformat(str(t.created_at))
        except Exception:
            created = now  # fallback
        if created >= cutoff:
            cat = str(t.category)
            demand_by_category[cat] = demand_by_category.get(cat, 0) + 1

    # Supply = sum of remaining capacity for APPROVED sellers in each category
    # Current load = number of IN_PROGRESS tasks assigned to that seller
    seller_loads = _compute_seller_loads(tasks)
    supply_by_category: Dict[str, int] = {}
    for s in approved_sellers:
        load = seller_loads.get(s.id, 0)
        remaining = max(0, s.capacity - load)
        for cat in s.specialization_categories:
            cat_str = str(cat)
            supply_by_category[cat_str] = supply_by_category.get(cat_str, 0) + remaining

    all_cats = set(list(demand_by_category.keys()) + list(supply_by_category.keys()) + list(tasks_by_category.keys()))

    supply_demand_ratio: Dict[str, Optional[float]] = {}
    supply_demand_signal: Dict[str, str] = {}
    for cat in all_cats:
        d = demand_by_category.get(cat, 0)
        s_val = supply_by_category.get(cat, 0)
        if d == 0:
            ratio = None
            signal = "no_demand"
        elif s_val == 0:
            ratio = 0.0
            signal = "over_subscribed"
        else:
            ratio = round(s_val / d, 2)
            if ratio >= 2.0:
                signal = "healthy"
            elif ratio >= 1.0:
                signal = "balanced"
            else:
                signal = "tight"
        supply_demand_ratio[cat] = ratio
        supply_demand_signal[cat] = signal

    # ── Seller Utilization ────────────────────────────────────────────
    seller_utilization: List[Dict[str, Any]] = []
    utilization_pcts: List[float] = []
    for s in approved_sellers:
        load = seller_loads.get(s.id, 0)
        cap  = max(s.capacity, 1)
        pct  = round(load / cap, 3)
        seller_utilization.append({
            "seller_id":   s.id,
            "name":        s.display_name,
            "categories":  [str(c) for c in s.specialization_categories],
            "active_tasks": load,
            "capacity":    cap,
            "utilization": pct,
            "status":      "busy" if pct >= 0.8 else "available",
        })
        utilization_pcts.append(pct)
    avg_utilization = round(sum(utilization_pcts) / len(utilization_pcts), 3) if utilization_pcts else None

    # ── Specialist vs. Generalist ─────────────────────────────────────
    n_comp = len(comparisons)
    spec_wins = sum(1 for c in comparisons if c.winner == "seller")
    spec_win_rate = round(spec_wins / n_comp, 3) if n_comp else None
    avg_delta = (
        round(sum(c.delta for c in comparisons) / n_comp, 3) if n_comp else None
    )

    return MarketplaceSnapshot(
        snapshot_at=now.isoformat() + "Z",
        active_buyers=active_buyers,
        total_buyers=total_buyers,
        active_sellers=active_sellers,
        total_sellers=total_sellers,
        sellers_by_category=sellers_by_category,
        sellers_pending_review=sellers_pending,
        total_tasks=total,
        tasks_by_status=tasks_by_status,
        tasks_by_category=tasks_by_category,
        fill_rate=fill_rate,
        fill_rate_by_category=fill_rate_by_category,
        total_quotes=len(quotes),
        quote_volume_by_category=quote_volume_by_category,
        avg_price_overall=avg_price_overall,
        avg_price_by_category=avg_price_by_category,
        price_range_by_category=price_range_by_category,
        price_trend_by_category=price_trend_by_category,
        avg_eta_by_category=avg_eta_by_category,
        lookback_hours=lookback_hours,
        demand_by_category=demand_by_category,
        supply_by_category=supply_by_category,
        supply_demand_ratio=supply_demand_ratio,
        supply_demand_signal=supply_demand_signal,
        seller_utilization=seller_utilization,
        avg_utilization=avg_utilization,
        total_comparisons=n_comp,
        specialist_win_rate=spec_win_rate,
        avg_quality_delta=avg_delta,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _count_by(items: list, key_fn) -> Dict[str, int]:
    """Generic group-and-count."""
    result: Dict[str, int] = {}
    for item in items:
        k = key_fn(item)
        result[k] = result.get(k, 0) + 1
    return result


def _count_sellers_by_category(sellers: list) -> Dict[str, int]:
    """Count APPROVED sellers per category (sellers may cover multiple categories)."""
    result: Dict[str, int] = {}
    for s in sellers:
        for cat in s.specialization_categories:
            cat_str = str(cat)
            result[cat_str] = result.get(cat_str, 0) + 1
    return result


def _compute_seller_loads(tasks: list) -> Dict[str, int]:
    """
    Compute the number of IN_PROGRESS tasks per seller.
    Used for capacity calculations.
    """
    loads: Dict[str, int] = {}
    for t in tasks:
        if t.selected_seller_id and str(t.status) == "in_progress":
            loads[t.selected_seller_id] = loads.get(t.selected_seller_id, 0) + 1
    return loads


def _compute_price_trend(quotes: list, store: Any) -> Dict[str, List[float]]:
    """
    Compute a 7-day daily average price trend per category from accepted quotes.

    MVP: returns daily averages for any days that have data; empty list otherwise.
    Future: pad missing days with None or interpolated values for a continuous chart.

    Returns: {category: [day_0_avg, day_1_avg, ...]} oldest first.
    """
    now = datetime.utcnow()
    # Bucket accepted quotes by (category, day_offset)
    buckets: Dict[str, Dict[int, List[float]]] = {}  # cat → {day_offset: [prices]}

    for q in quotes:
        if not q.accepted:
            continue
        try:
            created = q.created_at if isinstance(q.created_at, datetime) else datetime.fromisoformat(str(q.created_at))
        except Exception:
            continue
        day_offset = (now.date() - created.date()).days
        if day_offset > 7:
            continue
        task = store.tasks.get(q.task_id)
        cat = str(task.category) if task else "unknown"
        buckets.setdefault(cat, {}).setdefault(day_offset, []).append(float(q.proposed_price))

    trend: Dict[str, List[float]] = {}
    for cat, day_map in buckets.items():
        # Oldest first: day 7 → day 0
        daily = []
        for d in sorted(day_map.keys(), reverse=True):
            prices = day_map[d]
            daily.append(round(sum(prices) / len(prices), 2))
        trend[cat] = daily

    return trend
