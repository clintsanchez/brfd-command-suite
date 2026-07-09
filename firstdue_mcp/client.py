"""
Thin, typed client over the First Due RMS REST API.

Base URL:  https://sizeup.firstduesizeup.com/fd-api/v1/
Auth:      OAuth2 Bearer token (personal API token, or minted from email/password).
Format:    JSON in/out, ISO 8601 UTC timestamps. Server-to-server only.

Only the endpoints backing the three targeted use cases are wrapped here:
Incidents/NFIRS, Hydrants/pre-plans, and Personnel/scheduling. Adding more is a
one-line method that calls ``self.request(...)``.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "https://sizeup.firstduesizeup.com/fd-api/v1"
DEFAULT_TIMEOUT = 30  # seconds


class FirstDueError(Exception):
    """A non-2xx response from the First Due API.

    Carries the HTTP status plus the API's structured error body
    (``{code, message}`` for 4xx, and a ``errors:[{field, code}]`` list for 422).
    """

    def __init__(
        self,
        status: int,
        message: str,
        code: Optional[int] = None,
        errors: Optional[list] = None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.errors = errors or []
        detail = f"HTTP {status}"
        if code is not None:
            detail += f" (code {code})"
        detail += f": {message}"
        if self.errors:
            detail += f" | field errors: {self.errors}"
        super().__init__(detail)


class FirstDueClient:
    """Authenticated session against the First Due API."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        enable_writes: bool = False,
    ):
        self.base_url = (base_url or os.environ.get("FIRSTDUE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.enable_writes = enable_writes
        self._token = token or os.environ.get("FIRSTDUE_API_TOKEN") or None
        self._session = requests.Session()

    # -- auth ---------------------------------------------------------------

    def mint_token(self, email: str, password: str) -> str:
        """Exchange email + password for a bearer token via ``POST /auth/token``.

        Only needed if you don't have a personal API token. Stores and returns it.
        """
        url = f"{self.base_url}/auth/token"
        resp = self._session.post(
            url,
            json={"email": email, "password": password, "grant_type": "client_credentials"},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        data = self._parse(resp)
        token = data.get("access_token") or data.get("token")
        if not token:
            raise FirstDueError(resp.status_code, f"No token in auth response: {data}")
        self._token = token
        return token

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        email = os.environ.get("FIRSTDUE_EMAIL")
        password = os.environ.get("FIRSTDUE_PASSWORD")
        if email and password:
            return self.mint_token(email, password)
        raise FirstDueError(
            401,
            "No API token available. Set FIRSTDUE_API_TOKEN, or FIRSTDUE_EMAIL + FIRSTDUE_PASSWORD.",
        )

    # -- core request -------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> Any:
        """Issue an authenticated request and return the parsed JSON body.

        ``params`` with ``None`` values are dropped. Writes (POST/PUT/PATCH/DELETE)
        raise unless the client was created with ``enable_writes=True``.
        """
        method = method.upper()
        if method not in ("GET", "HEAD") and not self.enable_writes:
            raise FirstDueError(
                403,
                f"Write operation {method} {path} blocked. "
                "Writes are disabled; set FIRSTDUE_ENABLE_WRITES=true to allow.",
            )
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self._session.request(
            method,
            url,
            params=params or None,
            json=json,
            headers={
                "Authorization": f"Bearer {self._ensure_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        return self._parse(resp)

    @staticmethod
    def _parse(resp: requests.Response) -> Any:
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            body = resp.json()
        except ValueError:
            body = None
        if not resp.ok:
            if isinstance(body, dict):
                raise FirstDueError(
                    resp.status_code,
                    body.get("message", resp.reason or "request failed"),
                    code=body.get("code"),
                    errors=body.get("errors"),
                )
            raise FirstDueError(resp.status_code, (resp.text or resp.reason or "request failed")[:500])
        return body

    # =======================================================================
    # Incidents / NFIRS
    # =======================================================================

    def list_fire_incidents(
        self,
        status_codes: Optional[str] = None,
        incident_number: Optional[str] = None,
        start_alarm_at: Optional[str] = None,
        end_alarm_at: Optional[str] = None,
        start_updated_at: Optional[str] = None,
        end_updated_at: Optional[str] = None,
        page: Optional[int] = None,
    ) -> Any:
        """GET /fire-incidents — list fire incident reports (500/page; use ``page``)."""
        return self.request(
            "GET",
            "/fire-incidents",
            params={
                "status_codes": status_codes,
                "incident_number": incident_number,
                "start_alarm_at": start_alarm_at,
                "end_alarm_at": end_alarm_at,
                "start_updated_at": start_updated_at,
                "end_updated_at": end_updated_at,
                "page": page,
            },
        )

    def iter_all_fire_incidents(self, max_pages: int = 10, **filters) -> Any:
        """Fetch multiple pages of /fire-incidents matching ``filters``.

        The endpoint returns ``{fire_incidents, total, pages}`` at 500 records/page.
        Fetches up to ``max_pages`` pages (default 10 = up to 5,000 records) and returns
        a combined envelope with ``pages_fetched`` and ``truncated`` so the caller knows
        whether more data remains. Keep ``max_pages`` modest — a full department can have
        hundreds of pages / 100k+ incidents.
        """
        first = self.list_fire_incidents(page=1, **filters)
        if not isinstance(first, dict):
            return first
        rows = list(first.get("fire_incidents", []))
        pages = first.get("pages", 1) or 1
        fetched = 1
        for page in range(2, min(pages, max_pages) + 1):
            nxt = self.list_fire_incidents(page=page, **filters)
            rows.extend(nxt.get("fire_incidents", []) if isinstance(nxt, dict) else [])
            fetched += 1
        return {
            "fire_incidents": rows,
            "total": first.get("total"),
            "pages": pages,
            "pages_fetched": fetched,
            "truncated": fetched < pages,
        }

    def get_nfirs_setting(self) -> Any:
        """GET /nfirs-setting — fire incident setup/config."""
        return self.request("GET", "/nfirs-setting")

    def get_nfirs_notification_by_id(self, notification_id: str) -> Any:
        """GET /nfirs-notifications/{id}."""
        return self.request("GET", f"/nfirs-notifications/{notification_id}")

    def get_nfirs_notification_by_number(self, incident_number: str) -> Any:
        """GET /nfirs-notifications/number/{incident_number}."""
        return self.request("GET", f"/nfirs-notifications/number/{incident_number}")

    # =======================================================================
    # Hydrants / pre-plans
    # =======================================================================

    def list_hydrants(
        self,
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
    ) -> Any:
        """GET /get-hydrants — list hydrants (paginated: 200/page via ``page``).

        The API requires at least one filter parameter (a bare call returns 422).
        Returns ``{current_page, total_pages, total_hydrant_records, has_more, items}``.
        """
        return self.request(
            "GET",
            "/get-hydrants",
            params={
                "id": id,
                "facility_code": facility_code,
                "hydrant_status_code": hydrant_status_code,
                "hydrant_type_code": hydrant_type_code,
                "fire_zone_id": fire_zone_id,
                "shift_id": shift_id,
                "assigned_to_user": assigned_to_user,
                "assigned_to_team": assigned_to_team,
                "service_date_from": service_date_from,
                "service_date_to": service_date_to,
                "flow_date_from": flow_date_from,
                "flow_date_to": flow_date_to,
                "xref_id": xref_id,
                "missing_hydrant_id": missing_hydrant_id,
                "missing_facility_code": missing_facility_code,
                "updated_after": updated_after,
                "page": page,
            },
        )

    def iter_all_hydrants(self, max_pages: int = 25, **filters) -> Any:
        """Fetch multiple pages of /get-hydrants (200/page) and combine ``items``.

        Requires at least one filter (same as ``list_hydrants``). Returns a combined
        envelope with ``pages_fetched`` and ``truncated``.
        """
        first = self.list_hydrants(page=1, **filters)
        if not isinstance(first, dict):
            return first
        items = list(first.get("items", []))
        total_pages = first.get("total_pages", 1) or 1
        fetched = 1
        for page in range(2, min(total_pages, max_pages) + 1):
            nxt = self.list_hydrants(page=page, **filters)
            items.extend(nxt.get("items", []) if isinstance(nxt, dict) else [])
            fetched += 1
        return {
            "items": items,
            "total_hydrant_records": first.get("total_hydrant_records"),
            "total_pages": total_pages,
            "pages_fetched": fetched,
            "truncated": fetched < total_pages,
        }

    def create_hydrant(self, body: dict) -> Any:
        """POST /create-hydrant. Requires hydrant_type_code, latitude, longitude."""
        return self.request("POST", "/create-hydrant", json=body)

    def update_hydrant(self, body: dict) -> Any:
        """PUT /update-hydrant. Body should carry an identifier (id/xref_id) plus fields."""
        return self.request("PUT", "/update-hydrant", json=body)

    def list_hydrant_flow_tests(
        self,
        firstdue_id: Optional[int] = None,
        facility_code: Optional[str] = None,
        hydrant_id: Optional[str] = None,
        completed_at_from: Optional[str] = None,
        completed_at_to: Optional[str] = None,
        most_recent: Optional[bool] = None,
    ) -> Any:
        """GET /get-hydrant-flow-tests."""
        return self.request(
            "GET",
            "/get-hydrant-flow-tests",
            params={
                "firstdue_id": firstdue_id,
                "facility_code": facility_code,
                "hydrant_id": hydrant_id,
                "completed_at_from": completed_at_from,
                "completed_at_to": completed_at_to,
                "most_recent": _bool01(most_recent),
            },
        )

    def list_hydrant_services(
        self,
        firstdue_id: Optional[int] = None,
        facility_code: Optional[str] = None,
        hydrant_id: Optional[str] = None,
        completed_at_from: Optional[str] = None,
        completed_at_to: Optional[str] = None,
        most_recent: Optional[bool] = None,
    ) -> Any:
        """GET /get-hydrant-services (inspections)."""
        return self.request(
            "GET",
            "/get-hydrant-services",
            params={
                "firstdue_id": firstdue_id,
                "facility_code": facility_code,
                "hydrant_id": hydrant_id,
                "completed_at_from": completed_at_from,
                "completed_at_to": completed_at_to,
                "most_recent": _bool01(most_recent),
            },
        )

    def set_hydrant_status(self, hydrant_id: int, status_code: Optional[str]) -> Any:
        """POST /set-hydrant-status. status_code: in_service | out_of_service | null.

        ``hydrant_id`` is the value from the hydrant's xref_id column.
        """
        return self.request(
            "POST",
            "/set-hydrant-status",
            json={"hydrant_id": hydrant_id, "status_code": status_code},
        )

    def list_caution_notes(self, page: Optional[int] = None) -> Any:
        """GET /preplans/units/caution-notes."""
        return self.request("GET", "/preplans/units/caution-notes", params={"page": page})

    # =======================================================================
    # Personnel / org / scheduling
    # =======================================================================

    def list_personnel(self) -> Any:
        """GET /personnel."""
        return self.request("GET", "/personnel")

    def list_personnel_detailed(self) -> Any:
        """GET /personnel/list — personnel with full details."""
        return self.request("GET", "/personnel/list")

    def list_stations(self) -> Any:
        """GET /stations."""
        return self.request("GET", "/stations")

    def list_shifts(self) -> Any:
        """GET /shifts."""
        return self.request("GET", "/shifts")

    def get_schedule(self, start: Optional[str] = None, end: Optional[str] = None) -> Any:
        """GET /schedule. ``start``/``end`` are ISO 8601; span capped at 31 days."""
        return self.request("GET", "/schedule", params={"start": start, "end": end})

    def list_response_zones(self) -> Any:
        """GET /response-zones."""
        return self.request("GET", "/response-zones")

    def list_fdids(self) -> Any:
        """GET /fdids."""
        return self.request("GET", "/fdids")


def _bool01(value: Optional[bool]) -> Optional[int]:
    """First Due boolean query params take 0/1."""
    if value is None:
        return None
    return 1 if value else 0
