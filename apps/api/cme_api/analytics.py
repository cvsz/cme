from dataclasses import dataclass
from datetime import datetime, UTC

SUPPORTED={"impression","click","cart","order","conversion","commission"}

@dataclass(frozen=True)
class AnalyticsEvent:
    tenant_id: str
    event_id: str
    type: str
    occurred_at: datetime
    measures: dict[str,float]

    def __post_init__(self):
        if self.type not in SUPPORTED:
            raise ValueError("unsupported analytics event type")

def dedupe(events: list[AnalyticsEvent]) -> list[AnalyticsEvent]:
    seen=set(); result=[]
    for event in events:
        key=(event.tenant_id,event.event_id)
        if key not in seen:
            seen.add(key); result.append(event)
    return result

def summarize_funnel(events: list[AnalyticsEvent]) -> dict[str,float]:
    counts={k:0 for k in ("impression","click","cart","order","conversion")}
    for event in events:
        if event.type in counts: counts[event.type]+=1
    return {**counts,"click_through_rate":counts["click"]/counts["impression"] if counts["impression"] else 0.0,"conversion_rate":counts["conversion"]/counts["click"] if counts["click"] else 0.0}
