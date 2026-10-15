# Project 5: Mixtape Bug Hunt

**Student:** Brian Too  
**Course:** CodePath AI201  
**Branch:** `bugfix/mixtape`

## AI usage

This project was completed with substantial Codex assistance at my request. Codex read the starter, traced the code, implemented fixes, ran checks, and drafted this document. The investigation and verification described below are agent-executed; they are not a claim that I independently performed those actions. Specific debugging examples and results are recorded as the work progresses.

## Codebase map — orientation before bug work

This section was written and committed before reproductions or implementation changes. It describes the starter's architecture.

| File or area | Responsibility |
| --- | --- |
| `app.py` | Owns the shared SQLAlchemy `db`, builds the Flask app with `create_app(config)`, accepts configuration overrides, registers four route blueprints, and creates database tables. The default database is SQLite. |
| `models.py` | Defines `User`, `Tag`, `Song`, `ListeningEvent`, `Rating`, `Playlist`, and `Notification`, including JSON serializers. `friendships` links users, `song_tags` links songs and tags, and `playlist_entries` stores playlist membership with explicit `position`, `added_by`, and `added_at` metadata. Each user/song pair has a unique rating. |
| `routes/songs.py` | Parses search, rating, and listening requests; invokes the corresponding services; serializes song, rating, or listening-event responses. |
| `routes/playlists.py` | Exposes playlist creation, metadata, ordered song retrieval, and adding a song. It delegates reads to the playlist service and additions to the notification service. |
| `routes/users.py` | Reads a profile directly from the database, delegates streak and notification reads, and exposes marking a notification as read. |
| `routes/feed.py` | Exposes listening-now and activity endpoints and wraps each result with a count. |
| `services/streak_service.py` | Records listening events, updates a user's stored listening streak and last-listened timestamp, and retrieves the streak. |
| `services/feed_service.py` | Selects friends' listening events, builds friend/song response objects, and reduces listening-now results to the latest event per friend. The separate activity feed returns recent events with a limit. |
| `services/search_service.py` | Performs case-insensitive title/artist searches and retrieves individual songs; serialized results include tag names. |
| `services/notification_service.py` | Saves or updates ratings, adds songs to playlists, persists notification rows, lists notifications, and marks them read. These interaction operations are grouped with notification handling. |
| `services/playlist_service.py` | Creates playlists, reads metadata, retrieves songs ordered by the association table's position, and lists a user's playlists. |
| `seed_data.py` | Recreates a local database with five users, friendships, songs and tags, listening events, three playlists, and a sample playlist notification. |
| `tests/test_streaks.py`, `tests/test_search.py`, `tests/test_playlists.py` | Use isolated in-memory SQLite databases to check service behavior with controlled fixtures. |
| `requirements.txt`, `.gitignore` | Declare Flask, SQLAlchemy, dotenv, and pytest dependencies; keep virtual environments, local databases, and environment files out of Git. |

### Data flow: rating a song

1. `POST /songs/<song_id>/rate` reaches `rate()` in `routes/songs.py`.
2. The route reads `user_id` and `score`, checks required fields, converts the score to an integer, and calls `notification_service.rate_song()`.
3. The service validates the score range, fetches the `Song` and rating `User`, and queries `Rating` by the `(user_id, song_id)` pair.
4. It changes the existing rating's score or adds a new `Rating`, then commits the database transaction.
5. The route serializes the returned rating with `to_dict()` and sends a JSON response with status 201. Validation errors become status 400 responses.

### Data flow: friends' listening feed

`GET /feed/<user_id>/listening-now` → `routes/feed.py:listening_now()` → `get_friends_listening_now()` → look up the user and their `friends` relationship → query `ListeningEvent` rows for those friend IDs and the time cutoff → sort newest first → retain the first event for each friend → fetch its `User` and `Song` → serialize the feed and count.

### Organization patterns

The routes usually handle HTTP input/output while services handle database queries and business rules. The profile route is a small direct-query exception. Model serializers define response shapes. Services raise `ValueError` for many invalid IDs or inputs, which routes translate into JSON errors. Dates are generated in UTC; there is no per-user timezone field. Playlist order comes from association metadata, not song titles or unordered relationship iteration.

## Root cause analyses

### **Issue #1 — My listening streak keeps resetting**

**How you reproduced it:** Before changing services, the starter's Sunday test failed (`1` instead of `2`). The added HTTP regression set `friend.listening_streak = 12` and `last_listened_at` to Saturday, October 10, 2026, at 09:00 UTC. With the streak service clock fixed at Sunday, October 11, 09:00 UTC, `POST /songs/song/listen` succeeded, but `GET /users/friend/streak` returned `1` instead of `13`. The same fixture for each other weekday passed. See `evidence/regressions-before.txt`.

**How you found the root cause:** The investigation followed `routes/songs.py:listen()` → `record_listening_event()` → `update_listening_streak()` in `services/streak_service.py`, then checked `routes/users.py:streak()` and `get_streak()` to establish that the GET simply reads the stored counter. `models.py` showed the counter and timestamp on `User`. The decisive observation was that a one-day gap still fell through to the reset branch when `today.weekday()` was 6; the parameterized endpoint test isolated Sunday as the failing weekday.

**The root cause:** `elif days_since_last == 1 and today.weekday() != 6` adds an unrelated weekday restriction to the consecutive-day rule. Python numbers Sunday as 6, so Saturday-to-Sunday listening resets the counter even though `(today - last_date).days` equals 1. Calendar continuity depends on the date difference, not the name of the weekday; excluding Sunday contradicts the service's documented streak rules.

**Your fix:** Removed `and today.weekday() != 6`. A one-day gap now increments on every weekday. The existing first-listen, same-day, and skipped-day branches remain in place.

**Your side-effect check:** Ran the five original streak tests and nine added endpoint cases: all 14 passed. The new cases cover all seven weekdays, a second listen on the same day (two events saved but only one streak increment), a month boundary landing on Sunday, and a year boundary with naive UTC database timestamps. The original tests also verify initialization and reset after a skipped day. These checks target both the changed branch and adjacent branches that could accidentally be disturbed.

**Regression tests:** `tests/test_issue1_streak_regression.py`; the Sunday and November 1 cases failed before the fix.

