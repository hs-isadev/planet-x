"""Public NEOSSat footprint cross-check via the CADC TAP service."""
import csv
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from astropy.time import Time
from fastapi import Query

CADC_TAP = "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync"
CADC_PACKAGE = "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/caom2ops/pkg"
CAP = 30


def neossat_query(ra, dec):
    today = datetime.now(timezone.utc).date().isoformat()
    return (f"SELECT TOP {CAP} o.observationID, p.productID, p.planeURI, p.time_bounds_lower "
            "FROM caom2.Observation AS o JOIN caom2.Plane AS p ON o.obsID=p.obsID "
            f"WHERE o.collection='NEOSSAT' AND p.dataRelease < '{today}' "
            f"AND CONTAINS(POINT('ICRS',{ra:.8f},{dec:.8f}),p.position_bounds)=1 "
            "ORDER BY p.time_bounds_lower DESC")


def partner_coverage(ra, dec):
    query = neossat_query(ra, dec)
    params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query}
    query_url = CADC_TAP + "?" + urlencode(params)
    try:
        response = requests.get(CADC_TAP, params=params, timeout=(5, 11))
        response.raise_for_status()
        csv_rows = csv.DictReader(response.text.splitlines())
        expected = {"observationid", "productid", "planeuri", "time_bounds_lower"}
        if not csv_rows.fieldnames or not expected.issubset({v.lower() for v in csv_rows.fieldnames}):
            raise ValueError("CADC returned an invalid result table.")
        rows = []
        for values in csv_rows:
            row = {key.lower(): value for key, value in values.items()}
            uri = row["planeuri"]
            if not uri or not uri.upper().startswith("CAOM:NEOSSAT/"):
                continue
            date = None
            if row["time_bounds_lower"]:
                date = Time(float(row["time_bounds_lower"]), format="mjd").isot + "Z"
            rows.append(dict(observation_id=row["observationid"], product_id=row["productid"],
                date_utc=date, archive_url=CADC_PACKAGE+"?"+urlencode({"ID":uri})))
        return dict(status="ok", records=rows, limit=CAP, capped=len(rows)==CAP, query_url=query_url)
    except (requests.RequestException, ValueError, TypeError):
        return dict(status="unavailable", records=[], query_url=query_url)


def install_partner_routes(app):
    @app.get("/api/partners/neossat")
    def neossat(ra: float = Query(ge=0, lt=360), dec: float = Query(ge=-90, le=90)):
        return partner_coverage(ra, dec)
