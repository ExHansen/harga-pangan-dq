"""Generate static data files for the GitHub Pages evidence site.

Reads from the DuckDB warehouse (built by ``dbt build``) and writes JSON/CSV files
into the ``data/site/`` directory. This is called by the ``daily.yml`` workflow
after ingestion and dbt build.
"""

import csv
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _sql(sql: str, warehouse_path: Path) -> list[dict]:
    """Run a SQL query against the DuckDB warehouse and return rows as dicts."""
    import duckdb

    con = duckdb.connect(str(warehouse_path))
    try:
        con.execute("SET TimeZone = 'UTC'")
        result = con.execute(sql).fetchall()
        cols = [d[0] for d in con.description] if con.description else []
        return [dict(zip(cols, row, strict=False)) for row in result]
    finally:
        con.close()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", path)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=rows[0].keys(), lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)
    logger.info("wrote %s (%d rows)", path, len(rows))


def deploy(
    warehouse_path: Path,
    out_dir: Path | None = None,
) -> None:
    """Generate all static site data files."""
    out = out_dir or Path("data/site")
    out.mkdir(parents=True, exist_ok=True)

    # --- Latest prices ---
    latest_prices_sql = """
        SELECT
            c.commodity_name,
            p.source_province_name,
            p.price_date,
            p.price_idr,
            p.dod_pct,
            p.wow_pct,
            p.gap_to_national_pct
        FROM fct_price_daily p
        JOIN dim_commodity c ON p.commodity_id = c.commodity_id
        WHERE p.price_date = (SELECT MAX(price_date) FROM fct_price_daily)
        ORDER BY c.commodity_name, p.source_province_name
    """
    latest_rows = _sql(latest_prices_sql, warehouse_path)
    as_of = latest_rows[0]["price_date"].isoformat() if latest_rows else None
    _write_json(
        out / "latest_prices.json",
        {"as_of_date": as_of, "rows": latest_rows},
    )
    _write_csv(out / "latest_prices.csv", latest_rows)

    # --- Volatility ---
    volatility_sql = """
        SELECT
            c.commodity_name,
            v.area_type,
            v.area_name,
            v.volatility_60,
            v.mean_abs_dod_pct,
            v.max_abs_dod_pct,
            v.n_returns,
            v.as_of_date
        FROM agg_volatility v
        JOIN dim_commodity c ON v.commodity_id = c.commodity_id
        ORDER BY v.volatility_60 DESC NULLS LAST
    """
    vol_rows = _sql(volatility_sql, warehouse_path)
    _write_json(out / "volatility.json", {"rows": vol_rows})
    _write_csv(out / "volatility.csv", vol_rows)

    # --- Gap to national (latest per commodity x province) ---
    gap_sql = """
        WITH latest AS (
            SELECT MAX(price_date) AS max_date
            FROM fct_price_daily
        )
        SELECT
            c.commodity_name,
            p.source_province_name,
            p.price_date,
            p.gap_to_national_pct
        FROM fct_price_daily p
        JOIN dim_commodity c ON p.commodity_id = c.commodity_id
        JOIN latest l ON p.price_date = l.max_date
        ORDER BY ABS(p.gap_to_national_pct) DESC
        LIMIT 500
    """
    gap_rows = _sql(gap_sql, warehouse_path)
    _write_json(out / "gap_to_national.json", {"rows": gap_rows})
    _write_csv(out / "gap_to_national.csv", gap_rows)

    # --- Health checks summary ---
    check_results_path = warehouse_path.parent / "check_results.json"
    if check_results_path.exists():
        check_data = json.loads(check_results_path.read_text(encoding="utf-8"))
        health = {
            "date": check_data.get("business_date", as_of),
            "checks": [
                {
                    "name": c["name"],
                    "passed": c["passed"],
                    "details": f"{len([i for i in check_data.get('incidents', []) if i.get('check_name') == c['name']])} insiden",
                }
                for c in check_data.get("checks", [])
            ],
        }
    else:
        health = {"date": as_of, "checks": []}
    _write_json(out / "health.json", health)
    _write_csv(out / "health.csv", health.get("checks", []))

    # --- Contracts (from dbt test results) ---
    # Read dbt test results if available
    contracts = _read_dbt_tests(warehouse_path.parent)
    _write_json(out / "contracts.json", {"contracts": contracts})

    # --- Incidents ---
    incidents_path = warehouse_path.parent / "incidents" / "incident_events.db"
    if incidents_path.exists():
        import duckdb as ddb

        con = ddb.connect(str(incidents_path))
        try:
            con.execute("SET TimeZone = 'UTC'")
            result = con.execute('SELECT * FROM incident_events ORDER BY "at" DESC').fetchall()
            cols = [d[0] for d in con.description] if con.description else []
            incident_rows = [dict(zip(cols, row, strict=False)) for row in result]
        finally:
            con.close()
    else:
        incident_rows = []
    _write_json(out / "incidents.json", {"events": incident_rows})
    _write_csv(out / "incidents.csv", incident_rows)

    logger.info("deploy complete: %s", out)


def _read_dbt_tests(build_dir: Path) -> list[dict]:
    """Read dbt test results from the target directory."""
    target_dir = build_dir / "dbt" / "target"
    if not (target_dir / "run_results.json").exists():
        return []

    run_results = json.loads((target_dir / "run_results.json").read_text(encoding="utf-8"))
    contracts = []
    for node in run_results.get("results", []):
        if node.get("status") == "pass" and "test" in node.get("unique_id", ""):
            name = node.get("name", "")
            if "contract" in name.lower() or "enforced" in name.lower():
                contracts.append({"model": name, "passed": True})
        elif node.get("status") == "error" and "test" in node.get("unique_id", ""):
            name = node.get("name", "")
            if "contract" in name.lower() or "enforced" in name.lower():
                contracts.append({"model": name, "passed": False})
    return contracts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warehouse = Path(os.environ.get("HPDQ_WAREHOUSE", "build/warehouse.duckdb"))
    out = Path(os.environ.get("HPDQ_DEPLOY_OUT", "data/site"))
    deploy(warehouse, out)


if __name__ == "__main__":
    main()
