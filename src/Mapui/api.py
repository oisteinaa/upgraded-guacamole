"""Investigation API: bounded reads, explicit provenance, atomic audited reviews."""

import logging
import os
from datetime import datetime, timedelta
from typing import Literal

import psycopg2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.gzip import GZipMiddleware

from .db import ROOT, database, rows
from .signals import read_signal

app = FastAPI(title="Sensnet Cable Observatory", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=3)


@app.exception_handler(psycopg2.Error)
def database_error(request, exc):
    logging.getLogger(__name__).exception("Database request failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database unavailable or local migrations missing. Check the server log and database configuration."
        },
    )


@app.middleware("http")
async def same_origin(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        allowed = {
            str(request.base_url).rstrip("/"),
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }
        if origin and origin not in allowed:
            return JSONResponse(
                status_code=403, content={"detail": "Cross-origin writes are disabled"}
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/overview")
def overview():
    counts = rows("""SELECT count(*) AS events, count(*) FILTER (WHERE classid IS NULL) AS unclassified,
                     min(time) AS first_event, max(time) AS last_event FROM events""")[
        0
    ]
    counts.update(
        rows("""SELECT (SELECT count(*) FROM masts) AS masts,
                         (SELECT count(*) FROM mast_spans) AS spans,
                         (SELECT count(*) FROM das_recordings) AS recordings,
                         (SELECT count(*) FROM event_context WHERE alignment_verified) AS aligned""")[
            0
        ]
    )
    return {
        "mapping_lids": [
            r["lid"] for r in rows("SELECT DISTINCT lid FROM masteliste ORDER BY lid")
        ],
        "counts": counts,
        "classes": rows("SELECT * FROM event_classes ORDER BY classid"),
        "routes": rows("SELECT route,name FROM mast_routes ORDER BY route"),
        "stations": rows("SELECT lid,name FROM weather_stations ORDER BY lid"),
        "environment": os.getenv("DAS_ENVIRONMENT", "Local investigation"),
        "write_enabled": os.getenv("DAS_REVIEW_WRITES", "1") == "1",
        "legacy_time_note": "Legacy event/weather timestamps have no timezone. Shown as stored; alignment requires verified writer convention.",
    }


def event_filter(start, end, classid, route, review, search):
    clauses, args = [], []
    if start:
        clauses.append("e.time >= %s")
        args.append(start)
    if end:
        clauses.append("e.time < %s")
        args.append(end)
    if classid == 0:
        clauses.append("e.classid IS NULL")
    elif classid is not None:
        clauses.append("e.classid=%s")
        args.append(classid)
    if route:
        clauses.append("ctx.route=%s AND ctx.alignment_verified")
        args.append(route)
    if review in ("reviewed", "unreviewed"):
        clauses.append(
            ("NOT " if review == "unreviewed" else "")
            + "EXISTS (SELECT 1 FROM event_reviews r WHERE r.event_id=e.id)"
        )
    if search:
        clauses.append("(e.comment ILIKE %s OR e.id::text=%s)")
        args.extend(["%" + search + "%", search])
    return " AND ".join(clauses) or "true", args


EVENT_JOIN = """FROM events e LEFT JOIN event_classes c ON c.classid=e.classid
 LEFT JOIN event_data_types t ON t.data_type=e.type LEFT JOIN event_context ctx ON ctx.event_id=e.id"""
EVENT_COLUMNS = """e.id,e.time,e.type,e.value,e.comment,e.classid, c.name AS class_name,
 t.name AS metric,ctx.route,ctx.alignment_verified,ctx.channel,ctx.lid,
 (SELECT count(*) FROM event_reviews r WHERE r.event_id=e.id) AS revision"""


@app.get("/api/events")
def events(
    start: datetime | None = None,
    end: datetime | None = None,
    classid: int | None = Query(None, ge=0, le=32767),
    route: str | None = None,
    review: Literal["all", "reviewed", "unreviewed"] = "all",
    search: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(50, ge=1, le=200),
):
    if any(d and d.tzinfo for d in (start, end)):
        raise HTTPException(
            422, "Legacy filters require stored timestamps without timezone offsets"
        )
    if start and end and end <= start:
        raise HTTPException(422, "End must be after start")
    where, args = event_filter(start, end, classid, route, review, search)
    with database() as cur:
        cur.execute("SELECT count(*) AS n " + EVENT_JOIN + " WHERE " + where, args)
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT "
            + EVENT_COLUMNS
            + " "
            + EVENT_JOIN
            + " WHERE "
            + where
            + " ORDER BY e.time DESC,e.id DESC LIMIT %s OFFSET %s",
            args + [limit, offset],
        )
        items = list(cur.fetchall())
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@app.get("/api/events/{event_id}")
def event_detail(event_id: int):
    found = rows(
        "SELECT " + EVENT_COLUMNS + " " + EVENT_JOIN + " WHERE e.id=%s", (event_id,)
    )
    if not found:
        raise HTTPException(404, "Event not found")
    item = found[0]
    item["reviews"] = rows(
        """SELECT r.*,c.name AS class_name FROM event_reviews r
                              LEFT JOIN event_classes c ON c.classid=r.classid
                              WHERE event_id=%s ORDER BY r.id DESC""",
        (event_id,),
    )
    context = rows("SELECT * FROM event_context WHERE event_id=%s", (event_id,))
    item["context"] = context[0] if context else None
    return item


class Review(BaseModel):
    classid: int | None = Field(None, ge=1, le=32767)
    expected_revision: int = Field(ge=0)
    expected_classid: int | None = Field(None, ge=1, le=32767)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewer", "note")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()


@app.post("/api/events/{event_id}/reviews")
def save_review(event_id: int, review: Review):
    if os.getenv("DAS_REVIEW_WRITES", "1") != "1":
        raise HTTPException(403, "Review writes are disabled")
    with database(write=True) as cur:
        cur.execute("SELECT classid FROM events WHERE id=%s FOR UPDATE", (event_id,))
        event = cur.fetchone()
        if not event:
            raise HTTPException(404, "Event not found")
        cur.execute(
            "SELECT count(*) AS revision FROM event_reviews WHERE event_id=%s",
            (event_id,),
        )
        if (
            cur.fetchone()["revision"] != review.expected_revision
            or event["classid"] != review.expected_classid
        ):
            raise HTTPException(
                409, "This event changed since you opened it. Reload it before saving."
            )
        if review.classid is not None:
            cur.execute(
                "SELECT 1 FROM event_classes WHERE classid=%s", (review.classid,)
            )
            if not cur.fetchone():
                raise HTTPException(422, "Unknown event class")
        cur.execute(
            """INSERT INTO event_reviews(event_id,previous_classid,classid,reviewer,note)
                       VALUES (%s,%s,%s,%s,%s)""",
            (event_id, event["classid"], review.classid, review.reviewer, review.note),
        )
        cur.execute(
            "UPDATE events SET classid=%s WHERE id=%s", (review.classid, event_id)
        )
    return event_detail(event_id)


def collection(features):
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/map")
def map_data():
    masts = rows(
        "SELECT id,route,mast,latitude,longitude,lid,channel,channel_distance_m FROM masts ORDER BY route,route_position"
    )
    spans = rows("SELECT * FROM v_mast_spans ORDER BY route,span_order")
    return {
        "masts": collection(
            [
                {
                    "type": "Feature",
                    "id": m["id"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [m["longitude"], m["latitude"]],
                    },
                    "properties": m,
                }
                for m in masts
            ]
        ),
        "spans": collection(
            [
                {
                    "type": "Feature",
                    "id": s["span_id"],
                    "geometry": s.pop("geometry_geojson"),
                    "properties": s,
                }
                for s in spans
            ]
        ),
    }


@app.get("/api/map/events")
def event_locations(
    start: datetime | None = None,
    end: datetime | None = None,
    classid: int | None = Query(None, ge=0, le=32767),
    route: str | None = None,
    review: Literal["all", "reviewed", "unreviewed"] = "all",
    search: str = Query("", max_length=100),
):
    if any(d and d.tzinfo for d in (start, end)):
        raise HTTPException(
            422, "Legacy filters require stored timestamps without timezone offsets"
        )
    if start and end and end <= start:
        raise HTTPException(422, "End must be after start")
    where, args = event_filter(start, end, classid, route, review, search)
    items = rows(
        "SELECT "
        + EVENT_COLUMNS
        + """,m.latitude,m.longitude """
        + EVENT_JOIN
        + """
        JOIN masteliste m ON m.channel=ctx.channel AND m.lid=ctx.lid
        WHERE ctx.alignment_verified AND """
        + where
        + " ORDER BY e.time DESC,e.id DESC LIMIT 5000",
        args,
    )
    return {
        "data": collection(
            [
                {
                    "type": "Feature",
                    "id": e["id"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [e["longitude"], e["latitude"]],
                    },
                    "properties": e,
                }
                for e in items
            ]
        ),
        "limit": 5000,
    }


@app.get("/api/recordings")
def recordings():
    return rows("""SELECT id,relative_path,acquisition_epoch,dt,samples,unit,lid,time_verified,mapping_verified,
                  processing,cardinality(channels) AS channel_count,channels[1] AS first_channel
                  FROM das_recordings ORDER BY acquisition_epoch DESC LIMIT 500""")


def get_recording(recording_id):
    found = rows("SELECT * FROM das_recordings WHERE id=%s", (recording_id,))
    if not found:
        raise HTTPException(404, "Recording not found")
    return found[0]


@app.get("/api/fibre")
def fibre(lid: int):
    from .metrics import fibre_positions

    try:
        points = fibre_positions(lid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return collection(
        [
            {
                "type": "Feature",
                "id": p["channel"],
                "geometry": {
                    "type": "Point",
                    "coordinates": [p["longitude"], p["latitude"]],
                },
                "properties": p,
            }
            for p in points
        ]
    )


@app.get("/api/recordings/{recording_id}/metrics")
def recording_metrics(
    recording_id: int,
    lid: int,
    frame: int = Query(0, ge=0),
    metric: Literal["ac_rms", "band_rms", "peak", "variance"] = "ac_rms",
    low: float = Query(1, gt=0, allow_inf_nan=False),
    high: float = Query(10, gt=0, allow_inf_nan=False),
):
    from .metrics import map_metrics

    try:
        return map_metrics(get_recording(recording_id), lid, frame, metric, low, high)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/recordings/{recording_id}/channels")
def recording_channels(recording_id: int):
    return get_recording(recording_id)["channels"]


@app.get("/api/recordings/{recording_id}/signal")
def signal(
    recording_id: int,
    channel: float = Query(..., allow_inf_nan=False),
    start: float = Query(0, ge=0, allow_inf_nan=False),
    duration: float = Query(10, gt=0, le=600, allow_inf_nan=False),
    points: int = Query(1600, ge=100, le=4000),
    channel_count: int | None = Query(None, ge=1),
    span_id: int | None = None,
):
    try:
        rec = get_recording(recording_id)
        bounds = None
        if span_id is not None:
            spans = rows("SELECT * FROM v_mast_spans WHERE span_id=%s", (span_id,))
            if not spans:
                raise ValueError("Span is unavailable")
            span = spans[0]
            if not rec["mapping_verified"] or rec["lid"] != span["from_lid"] or rec["lid"] != span["to_lid"]:
                raise ValueError("Span plotting requires a verified recording mapping for the span's DAS line")
            bounds = sorted([span["from_channel"], span["to_channel"]])
            channel = sum(bounds) / 2
            channel_count = None
        return read_signal(
            rec, channel, start, duration, points,
            channel_count=channel_count, channel_bounds=bounds,
        )
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/events/{event_id}/signal")
def event_signal(
    event_id: int,
    before: float = Query(5, ge=0, le=120, allow_inf_nan=False),
    after: float = Query(5, ge=0, le=120, allow_inf_nan=False),
    points: int = Query(1600, ge=100, le=4000),
):
    detail = event_detail(event_id)
    ctx = detail["context"]
    if not ctx or not ctx["alignment_verified"]:
        raise HTTPException(
            404, "No verified recording alignment exists for this event"
        )
    rec = get_recording(ctx["recording_id"])
    if (
        not rec["time_verified"]
        or not rec["mapping_verified"]
        or rec["lid"] != ctx["lid"]
    ):
        raise HTTPException(422, "Recording time or channel mapping is not verified")
    start = max(0, ctx["start_sample"] * rec["dt"] - before)
    end = min(rec["samples"] * rec["dt"], ctx["stop_sample"] * rec["dt"] + after)
    if ctx["stop_sample"] > rec["samples"] or end - start > 600:
        raise HTTPException(
            422, "Event window is invalid or too large; open recording directly"
        )
    try:
        result = read_signal(rec, ctx["channel"], start, end - start, points)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    result.update(
        event_start=ctx["start_sample"] * rec["dt"],
        event_end=ctx["stop_sample"] * rec["dt"],
    )
    return result


@app.get("/api/weather")
def weather(
    station: int,
    at: datetime,
    hours: float = Query(6, gt=0, le=72, allow_inf_nan=False),
):
    if at.tzinfo:
        raise HTTPException(
            422,
            "Weather uses stored wall-clock timestamps; timezone alignment is unverified",
        )
    result = rows(
        """SELECT w.time,w.value,t.abv,t.name,t.unit FROM weather_obs w
                   JOIN weather_obs_types t ON t.type=w.type
                   WHERE w.lid=%s AND w.time >= %s AND w.time <= %s ORDER BY w.time""",
        (station, at - timedelta(hours=hours), at),
    )
    latest = max((r["time"] for r in result), default=None)
    return {
        "items": result,
        "stale": latest is None or (at - latest).total_seconds() > 7200,
        "note": "Collected YR forecasts. Stored timestamps; no automatic alignment to DAS. Station selected by reviewer.",
    }


@app.get("/api/live")
def live():
    from .live import load_snapshot

    return load_snapshot()


DIST = ROOT / "web/dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
@app.get("/maps/")
def index():
    if not (DIST / "index.html").is_file():
        raise HTTPException(
            503, "Build the frontend first: cd web && npm ci && npm run build"
        )
    return FileResponse(DIST / "index.html")
