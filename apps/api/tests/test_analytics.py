from datetime import UTC, datetime
from cme_api.analytics import AnalyticsEvent, dedupe, summarize_funnel

def event(event_id,kind):
    return AnalyticsEvent("tenant-a",event_id,kind,datetime.now(UTC),{})

def test_dedupe_is_tenant_event_scoped():
    assert len(dedupe([event("1","click"),event("1","click")]))==1

def test_funnel_rates():
    result=summarize_funnel([event("1","impression"),event("2","impression"),event("3","click"),event("4","conversion")])
    assert result["click_through_rate"]==0.5
    assert result["conversion_rate"]==1.0
