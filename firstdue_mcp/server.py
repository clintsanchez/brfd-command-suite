"""
First Due RMS — MCP server.

Exposes the First Due REST API to Claude as MCP tools, scoped to three use cases:
Incidents/NFIRS, Hydrants/pre-plans, and Personnel/scheduling.

Run (stdio):   python -m firstdue_mcp.server
Config env:
  FIRSTDUE_API_TOKEN      personal API bearer token (preferred)
  FIRSTDUE_EMAIL / _PASSWORD   fallback: mint a token at startup
  FIRSTDUE_BASE_URL       override (default https://sizeup.firstduesizeup.com/fd-api/v1)
  FIRSTDUE_ENABLE_WRITES  "true" to allow create/update/status writes (default off)

Reads/writes:
  Read tools are always available. Write tools (create_hydrant, update_hydrant,
  set_hydrant_status) return an error unless FIRSTDUE_ENABLE_WRITES=true — a guard
  against unlogged data modification, per First Due's own security guidance.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    from pathlib import Path

    from dotenv import load_dotenv

    # Load .env from the project root (parent of this package), so the token is found
    # no matter what working directory Claude launches the server from.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv()  # also honor an already-present .env in cwd / env vars
except ImportError:  # dotenv is optional; env may already be set
    pass

from mcp.server.fastmcp import FastMCP

from .client import FirstDueClient, FirstDueError

WRITES_ENABLED = os.environ.get("FIRSTDUE_ENABLE_WRITES", "").strip().lower() in ("1", "true", "yes", "on")

mcp = FastMCP("first-due")
client = FirstDueClient(enable_writes=WRITES_ENABLED)


def _run(fn, *args, **kwargs) -> str:
    """Call a client method and return a JSON string, turning API errors into
    a readable message instead of an exception (so the tool result is usable)."""
    try:
        result = fn(*args, **kwargs)
    except FirstDueError as e:
        return json.dumps({"error": str(e), "status": e.status, "code": e.code, "field_errors": e.errors}, indent=2)
    except Exception as e:  # network/timeout/etc.
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2)
    return json.dumps(result, indent=2, default=str)


# Compact fields for a fire-incident summary — enough to identify/triage a record
# without the heavy nested lists (narratives, apparatuses, action_takens ~3.8KB each).
_INCIDENT_SUMMARY_FIELDS = (
    "incident_number", "status_code", "actual_incident_type", "alarm_at", "updated_at",
    "address", "city", "state", "zip_code", "first_due", "battalion",
    "alarms", "property_loss", "contents_loss",
)


def _shape_incidents(envelope, limit, summary) -> str:
    """Trim a /fire-incidents envelope for tool output: cap the record count and,
    when ``summary``, project each incident to a compact field set. Preserves
    ``total``/``pages`` and reports how many were returned vs. matched."""
    if not isinstance(envelope, dict) or "fire_incidents" not in envelope:
        return json.dumps(envelope, indent=2, default=str)  # error dict or unexpected shape
    rows = envelope.get("fire_incidents") or []
    matched = len(rows)
    if limit and limit > 0:  # limit<=0 means "no cap"
        rows = rows[:limit]
    if summary:
        rows = [{k: r.get(k) for k in _INCIDENT_SUMMARY_FIELDS} for r in rows]
    out = {
        "returned": len(rows),
        "matched_on_fetch": matched,
        "total": envelope.get("total"),
        "pages": envelope.get("pages"),
        "summary_mode": summary,
        "note": "Set summary=false for full records, or filter (incident_number / date range) "
                "to narrow. Records are 500/page; raise page or use all_pages for more.",
        "fire_incidents": rows,
    }
    if "pages_fetched" in envelope:
        out["pages_fetched"] = envelope["pages_fetched"]
        out["truncated"] = envelope["truncated"]
    return json.dumps(out, indent=2, default=str)


# ===========================================================================
# Incidents / NFIRS
# ===========================================================================

@mcp.tool()
def list_fire_incidents(
    status_codes: Optional[str] = None,
    incident_number: Optional[str] = None,
    start_alarm_at: Optional[str] = None,
    end_alarm_at: Optional[str] = None,
    start_updated_at: Optional[str] = None,
    end_updated_at: Optional[str] = None,
    page: Optional[int] = None,
    all_pages: bool = False,
    limit: int = 25,
    summary: bool = True,
) -> str:
    """List fire incident reports. There are ~112k incidents (500/page), so this
    tool trims output: it returns at most `limit` records and, by default, a compact
    `summary` projection. Always narrow with filters before pulling detail.

    Filters (all optional):
      status_codes: comma-delimited among incomplete, pending_authorization, authorized
      incident_number: exact incident report number (use this + summary=false for one full record)
      start_alarm_at / end_alarm_at: ISO 8601 alarm-time range
      start_updated_at / end_updated_at: ISO 8601 modified-time range (for incremental sync)
    Output control:
      page: 1-based page (500 records/page); all_pages: auto-paginate (heavy — use with filters)
      limit: max records to return (default 25; set 0 for no cap)
      summary: compact fields only (default true); false returns full records (~3.8KB each)
    """
    filters = dict(
        status_codes=status_codes,
        incident_number=incident_number,
        start_alarm_at=start_alarm_at,
        end_alarm_at=end_alarm_at,
        start_updated_at=start_updated_at,
        end_updated_at=end_updated_at,
    )
    try:
        if all_pages:
            envelope = client.iter_all_fire_incidents(**filters)
        else:
            envelope = client.list_fire_incidents(page=page, **filters)
    except FirstDueError as e:
        return json.dumps({"error": str(e), "status": e.status, "code": e.code, "field_errors": e.errors}, indent=2)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2)
    return _shape_incidents(envelope, limit, summary)


@mcp.tool()
def get_nfirs_setting() -> str:
    """Get the department's NFIRS / fire incident setup configuration."""
    return _run(client.get_nfirs_setting)


@mcp.tool()
def get_nfirs_notification(notification_id: Optional[str] = None, incident_number: Optional[str] = None) -> str:
    """Get one NFIRS notification, looked up by notification_id OR incident_number.

    Provide exactly one of the two identifiers.
    """
    if notification_id:
        return _run(client.get_nfirs_notification_by_id, notification_id)
    if incident_number:
        return _run(client.get_nfirs_notification_by_number, incident_number)
    return json.dumps({"error": "Provide either notification_id or incident_number."})


# ===========================================================================
# Hydrants / pre-plans
# ===========================================================================

@mcp.tool()
def list_hydrants(
    id: Optional[int] = None,
    facility_code: Optional[str] = None,
    hydrant_status_code: Optional[str] = None,
    hydrant_type_code: Optional[str] = None,
    fire_zone_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    assigned_to_user: Optional[int] = None,
    assigned_to_team: Optional[int] = None,
    service_date_from: Optional[str] = None,
    service_date_to: Optional[str] = None,
    flow_date_from: Optional[str] = None,
    flow_date_to: Optional[str] = None,
    xref_id: Optional[str] = None,
    missing_hydrant_id: Optional[str] = None,
    missing_facility_code: Optional[str] = None,
    updated_after: Optional[str] = None,
    page: Optional[int] = None,
    all_pages: bool = False,
) -> str:
    """List hydrants. Paginated at 200/page; response is
    {current_page, total_pages, total_hydrant_records, has_more, items}.

    At least one filter is REQUIRED (a bare call returns 422). Date params are ISO 8601:
    service_date_from/to = inspection date; flow_date_from/to = flow-test date;
    updated_after = records changed since. missing_hydrant_id / missing_facility_code
    return only records lacking that field. Use `page` for one page, or `all_pages=true`
    to auto-collect (up to 25 pages / 5,000 hydrants).
    """
    filters = dict(
        id=id,
        facility_code=facility_code,
        hydrant_status_code=hydrant_status_code,
        hydrant_type_code=hydrant_type_code,
        fire_zone_id=fire_zone_id,
        shift_id=shift_id,
        assigned_to_user=assigned_to_user,
        assigned_to_team=assigned_to_team,
        service_date_from=service_date_from,
        service_date_to=service_date_to,
        flow_date_from=flow_date_from,
        flow_date_to=flow_date_to,
        xref_id=xref_id,
        missing_hydrant_id=missing_hydrant_id,
        missing_facility_code=missing_facility_code,
        updated_after=updated_after,
    )
    if all_pages:
        return _run(client.iter_all_hydrants, **filters)
    return _run(client.list_hydrants, page=page, **filters)


@mcp.tool()
def list_hydrant_flow_tests(
    firstdue_id: Optional[int] = None,
    facility_code: Optional[str] = None,
    hydrant_id: Optional[str] = None,
    completed_at_from: Optional[str] = None,
    completed_at_to: Optional[str] = None,
    most_recent: Optional[bool] = None,
) -> str:
    """List hydrant flow tests. completed_at_from/to are ISO 8601 bounds;
    most_recent=true returns only the latest result per hydrant."""
    return _run(
        client.list_hydrant_flow_tests,
        firstdue_id=firstdue_id,
        facility_code=facility_code,
        hydrant_id=hydrant_id,
        completed_at_from=completed_at_from,
        completed_at_to=completed_at_to,
        most_recent=most_recent,
    )


@mcp.tool()
def list_hydrant_services(
    firstdue_id: Optional[int] = None,
    facility_code: Optional[str] = None,
    hydrant_id: Optional[str] = None,
    completed_at_from: Optional[str] = None,
    completed_at_to: Optional[str] = None,
    most_recent: Optional[bool] = None,
) -> str:
    """List hydrant services/inspections. Same params as flow tests."""
    return _run(
        client.list_hydrant_services,
        firstdue_id=firstdue_id,
        facility_code=facility_code,
        hydrant_id=hydrant_id,
        completed_at_from=completed_at_from,
        completed_at_to=completed_at_to,
        most_recent=most_recent,
    )


@mcp.tool()
def list_caution_notes(page: Optional[int] = None) -> str:
    """List pre-plan unit caution notes (paginated via page)."""
    return _run(client.list_caution_notes, page=page)


@mcp.tool()
def create_hydrant(hydrant: dict) -> str:
    """Create a hydrant. WRITE — requires FIRSTDUE_ENABLE_WRITES=true.

    Required keys in `hydrant`: hydrant_type_code (e.g. HYDRANT, CISTERN, Dry_Hydrant,
    DIPSITE, WATER_SOURCE, YARD_HYDRANT), latitude (number), longitude (number).
    Common optional keys: facility_code, xref_id, address, hydrant_status_code
    (in_service|out_of_service), manufacturer, model, num_outlet, main_size,
    static_pressure, residual_pressure, calculated_flow_rate, notes, fire_zone_id,
    fire_station_id, shift_id, assigned_user_id, inspected_at, last_flow_tested_at.
    """
    return _run(client.create_hydrant, hydrant)


@mcp.tool()
def update_hydrant(hydrant: dict) -> str:
    """Update a hydrant. WRITE — requires FIRSTDUE_ENABLE_WRITES=true.

    Include an identifier (id or xref_id) plus the fields to change. Field set mirrors
    create_hydrant. Response schema is undocumented; confirm against a known hydrant first.
    """
    return _run(client.update_hydrant, hydrant)


@mcp.tool()
def set_hydrant_status(hydrant_id: int, status_code: Optional[str]) -> str:
    """Set a hydrant's status. WRITE — requires FIRSTDUE_ENABLE_WRITES=true.

    hydrant_id is the hydrant's xref_id value. status_code: "in_service",
    "out_of_service", or null to clear.
    """
    return _run(client.set_hydrant_status, hydrant_id, status_code)


# ===========================================================================
# Personnel / org / scheduling
# ===========================================================================

@mcp.tool()
def list_personnel(detailed: bool = False) -> str:
    """List personnel. detailed=true uses /personnel/list (full details)."""
    if detailed:
        return _run(client.list_personnel_detailed)
    return _run(client.list_personnel)


@mcp.tool()
def list_stations() -> str:
    """List fire stations."""
    return _run(client.list_stations)


@mcp.tool()
def list_shifts() -> str:
    """List department/battalion shifts."""
    return _run(client.list_shifts)


@mcp.tool()
def get_schedule(start: Optional[str] = None, end: Optional[str] = None) -> str:
    """Get the schedule between start and end (ISO 8601). Span is capped at 31 days;
    defaults to today 00:00 -> tomorrow 00:00 when omitted."""
    return _run(client.get_schedule, start=start, end=end)


@mcp.tool()
def list_response_zones() -> str:
    """List response zones."""
    return _run(client.list_response_zones)


@mcp.tool()
def list_fdids() -> str:
    """List FDIDs (fire department identifiers)."""
    return _run(client.list_fdids)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
