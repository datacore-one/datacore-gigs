"""Liked artists, read from the library plur-buzz already maintains.

This module deliberately does NOT talk to Spotify. plur-buzz
(0-personal/2-code/plur-buzz) already holds an OAuth token with
``user-library-read`` and syncs Liked Songs into its SQLite DB. A second
integration would mean a second consent flow and a second token cache to
drift out of date, to obtain data that is already on disk.

Refreshing the library is plur-buzz's job: ``sync_likes_to_db()``.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from matcher import LikedArtist


class LibraryUnavailable(RuntimeError):
    """The Spotify library could not be read.

    Raised rather than returning an empty list, because "no artists" and "no
    library" produce the same empty briefing while meaning opposite things.
    """


def _split(artist_field: str) -> list[str]:
    """Spotify joins collaborators with ', '. Split there and nowhere else.

    Not on '&': 'Santi & Tuğçe' and 'Klik & Frik' are single acts.
    """
    return [part.strip() for part in (artist_field or "").split(", ") if part.strip()]


def load_liked_artists(db_path: str | Path, min_likes: int = 1) -> list[LikedArtist]:
    """Distinct artists in the library, weighted by how many tracks were liked."""
    path = Path(db_path).expanduser()
    if not path.exists():
        raise LibraryUnavailable(
            f"Spotify library not found at {path}.\n"
            "The gigs module reads the library plur-buzz maintains; it does not "
            "sync Spotify itself.\n"
            "Fix: run plur-buzz's likes sync, or set spotify_db_path in "
            "gigs.local.yaml if your checkout is elsewhere."
        )

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT artist, COUNT(*) AS n FROM tracks GROUP BY artist"
        ).fetchall()
    except sqlite3.Error as exc:  # unreadable / not the schema we expect
        raise LibraryUnavailable(f"Could not read {path}: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass

    counts: dict[str, int] = {}
    for artist_field, n in rows:
        for name in _split(artist_field):
            counts[name] = counts.get(name, 0) + int(n)

    artists = [LikedArtist(name, likes) for name, likes in counts.items()]
    artists = [a for a in artists if a.likes >= min_likes and a.key]
    artists.sort(key=lambda a: (-a.likes, a.name))
    return artists


def top_artists(artists: list[LikedArtist], limit: int) -> list[LikedArtist]:
    """The most-liked artists -- the ones worth spending a web search on."""
    return artists[: max(0, limit)]
