from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
    from backend.app import db_execute

    return db_execute(sql, params, fetch)


def _channel_dict(row):
    keys = ["id", "name", "country", "categories", "logo", "has_epg"]
    item = dict(zip(keys, row))
    item["has_epg"] = bool(item["has_epg"])
    return item


def _vod_dict(row, item_type: str):
    keys = ["id", "title", "year", "plot", "poster", "backdrop", "rating", "playable"]
    item = dict(zip(keys, row))
    item["item_type"] = item_type
    item["playable"] = bool(item["playable"])
    return item


def _live_rows(limit: int, offset: int = 0, q: str = "", country: str = "", category: str = ""):
    clauses = ["c.published=1"]
    params: list[object] = []
    if q:
        clauses.append("lower(c.name) LIKE ?")
        params.append(f"%{q.lower()}%")
    if country:
        clauses.append("c.country=?")
        params.append(country.upper())
    if category:
        clauses.append("c.categories LIKE ?")
        params.append(f"%{category}%")
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    return _db_execute(
        "SELECT c.id,c.name,c.country,c.categories,c.logo,"
        "CASE WHEN e.channel_id IS NULL THEN 0 ELSE 1 END AS has_epg "
        "FROM channels c LEFT JOIN epg_sources e ON e.channel_id=c.id "
        f"WHERE {where} "
        "AND EXISTS(SELECT 1 FROM streams s WHERE s.channel_id=c.id AND s.status IN ('healthy','degraded')) "
        "ORDER BY c.country,c.name LIMIT ? OFFSET ?",
        tuple(params),
        True,
    )


def _movie_rows(limit: int, offset: int = 0, q: str = ""):
    params: list[object] = []
    where = "m.published=1"
    if q:
        where += " AND lower(m.title) LIKE ?"
        params.append(f"%{q.lower()}%")
    params.extend([limit, offset])
    return _db_execute(
        "SELECT m.id,m.title,m.year,m.plot,m.poster,m.backdrop,m.rating,"
        "CASE WHEN EXISTS(SELECT 1 FROM vod_streams s WHERE s.item_id=m.id) THEN 1 ELSE 0 END AS playable "
        f"FROM vod_movies m WHERE {where} ORDER BY m.last_seen DESC,m.title LIMIT ? OFFSET ?",
        tuple(params),
        True,
    )


def _series_rows(limit: int, offset: int = 0, q: str = ""):
    params: list[object] = []
    where = "v.published=1"
    if q:
        where += " AND lower(v.title) LIKE ?"
        params.append(f"%{q.lower()}%")
    params.extend([limit, offset])
    return _db_execute(
        "SELECT v.id,v.title,v.year,v.plot,v.poster,v.backdrop,NULL AS rating,"
        "CASE WHEN EXISTS(SELECT 1 FROM vod_episodes e JOIN vod_streams s ON s.item_id=e.id "
        "WHERE e.series_id=v.id AND e.published=1) THEN 1 ELSE 0 END AS playable "
        f"FROM vod_series v WHERE {where} ORDER BY v.last_seen DESC,v.title LIMIT ? OFFSET ?",
        tuple(params),
        True,
    )


@router.get("/api/v1/home")
def home(limit: int = Query(12, ge=1, le=40)):
    live = [_channel_dict(row) for row in _live_rows(limit)]
    movies = [_vod_dict(row, "movie") for row in _movie_rows(limit)]
    series = [_vod_dict(row, "series") for row in _series_rows(limit)]
    return {
        "live": live,
        "movies": movies,
        "series": series,
        "sections": ["live", "movies", "series"],
    }


@router.get("/api/v1/live/channels")
def live_channels(
    q: str = Query(""),
    country: str = Query(""),
    category: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = _live_rows(limit, offset, q=q, country=country, category=category)
    return {
        "offset": offset,
        "limit": limit,
        "items": [_channel_dict(row) for row in rows],
    }


@router.get("/api/v1/catalog/{item_type}")
def catalog(
    item_type: str,
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if item_type == "movie":
        rows = _movie_rows(limit, offset, q=q)
    elif item_type == "series":
        rows = _series_rows(limit, offset, q=q)
    else:
        raise HTTPException(400, "item_type must be movie or series")
    return {
        "item_type": item_type,
        "offset": offset,
        "limit": limit,
        "items": [_vod_dict(row, item_type) for row in rows],
    }


@router.get("/api/v1/catalog/movie/{item_id}")
def movie_detail(item_id: str):
    rows = _db_execute(
        "SELECT m.id,m.title,m.original_title,m.year,m.plot,m.runtime,m.genres,m.country,m.language,m.rating,"
        "m.poster,m.backdrop,m.tmdb_id,m.imdb_id,m.rights_status,m.stream_status,"
        "CASE WHEN EXISTS(SELECT 1 FROM vod_streams s WHERE s.item_id=m.id) THEN 1 ELSE 0 END AS playable "
        "FROM vod_movies m WHERE m.id=? AND m.published=1 LIMIT 1",
        (item_id,),
        True,
    )
    if not rows:
        raise HTTPException(404, "Movie not found")
    keys = [
        "id", "title", "original_title", "year", "plot", "runtime", "genres", "country", "language",
        "rating", "poster", "backdrop", "tmdb_id", "imdb_id", "rights_status", "stream_status", "playable",
    ]
    item = dict(zip(keys, rows[0]))
    item["item_type"] = "movie"
    item["playable"] = bool(item["playable"])
    return item


@router.get("/api/v1/catalog/series/{series_id}")
def series_detail(series_id: str):
    rows = _db_execute(
        "SELECT id,title,original_title,year,plot,genres,poster,backdrop,tmdb_id,imdb_id,status,rights_status "
        "FROM vod_series WHERE id=? AND published=1 LIMIT 1",
        (series_id,),
        True,
    )
    if not rows:
        raise HTTPException(404, "Series not found")
    keys = [
        "id", "title", "original_title", "year", "plot", "genres", "poster", "backdrop", "tmdb_id", "imdb_id",
        "status", "rights_status",
    ]
    item = dict(zip(keys, rows[0]))
    seasons = _db_execute(
        "SELECT season_number,title,"
        "(SELECT COUNT(*) FROM vod_episodes e WHERE e.series_id=? AND e.season_number=s.season_number AND e.published=1) "
        "FROM vod_seasons s WHERE s.series_id=? ORDER BY season_number",
        (series_id, series_id),
        True,
    )
    item["item_type"] = "series"
    item["seasons"] = [
        {"season_number": row[0], "title": row[1] or f"Temporada {row[0]}", "episode_count": row[2]}
        for row in seasons
    ]
    return item


@router.get("/api/v1/series/{series_id}/episodes")
def series_episodes(series_id: str, season: int | None = Query(None, ge=0)):
    params: list[object] = [series_id]
    where = "e.series_id=? AND e.published=1"
    if season is not None:
        where += " AND e.season_number=?"
        params.append(season)
    rows = _db_execute(
        "SELECT e.id,e.season_number,e.episode_number,e.title,e.plot,e.air_date,e.duration,"
        "CASE WHEN EXISTS(SELECT 1 FROM vod_streams s WHERE s.item_id=e.id) THEN 1 ELSE 0 END AS playable "
        f"FROM vod_episodes e WHERE {where} ORDER BY e.season_number,e.episode_number",
        tuple(params),
        True,
    )
    keys = ["id", "season_number", "episode_number", "title", "plot", "air_date", "duration", "playable"]
    items = []
    for row in rows:
        item = dict(zip(keys, row))
        item["playable"] = bool(item["playable"])
        items.append(item)
    return {"series_id": series_id, "season": season, "items": items}


@router.get("/api/v1/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50)):
    return {
        "query": q,
        "live": [_channel_dict(row) for row in _live_rows(limit, q=q)],
        "movies": [_vod_dict(row, "movie") for row in _movie_rows(limit, q=q)],
        "series": [_vod_dict(row, "series") for row in _series_rows(limit, q=q)],
    }
