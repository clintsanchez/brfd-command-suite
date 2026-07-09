# Reference data

Static reference datasets used across the analyses.

## `nfirs_incident_types.csv` + `nfirs.py`

The NFIRS 5.0 **incident type** codeset (170 codes) mapping code → description, plus a small
loader. This is a published U.S. federal standard (USFA/FEMA National Fire Incident Reporting
System) and is in the public domain.

Use it to auto-label the `actual_incident_type` field from the First Due feed instead of
hand-mapping codes:

```python
from reference.nfirs import label, category
label("321")     # "EMS call, excluding vehicle accident with injury"
category("322")  # "Rescue / EMS"
```

> Note: this was built from the published NFIRS codeset rather than vendored from a repo — no
> clean code-lookup repository exists on GitHub (the candidates are ML projects or DB-import
> scripts with no lookup tables). The authoritative source is the USFA NFIRS documentation;
> FEMA's importer (`FEMA/nfirs-database-import`, CC0) holds the raw data pipeline but no code map.

First Due's own `dispatch_type_code` values (OM, DW, MVA, …) are department-specific and map ~1:1
to these NFIRS codes — see `analysis/derive_dispatch_codes.py` to (re)derive that mapping.
