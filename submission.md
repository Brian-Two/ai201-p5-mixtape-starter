# Project 5: Mixtape Bug Hunt

**Student:** Brian Too  
**Course:** CodePath AI201  
**Branch:** `bugfix/mixtape`

## AI usage

This project was completed with substantial Codex assistance at my request. Codex read the starter, traced the code, implemented fixes, ran checks, and drafted this document. The investigation and verification described below are agent-executed; they are not a claim that I independently performed those actions. Specific uses:

1. **Architecture and call-chain navigation:** Codex read `README.md`, `app.py`, the models, routes, and services to explain the responsibilities and trace the rating and feed flows. The architectural map was committed first (`2b2b8b3`), before reproduction tests or service edits. In particular, following `rate()` to `rate_song()` established where ratings are persisted and where notification work would need to be explicit.
2. **Search diagnosis:** Codex compared zero-, one-, and three-tag fixtures and traced the outer join through `.scalars().all()`. It explained why SQL rows can repeat an ORM identity. That explanation was verified by executing the original failing tests and an added API test that also preserves distinct same-title recordings and all tags; it was not accepted solely from generated prose.
3. **Boundary debugging:** Codex constructed fixed-clock tests for every weekday and for UTC midnight. These separated a Sunday-specific comparison from a date-gap issue, and a rolling 24-hour cutoff from a calendar-day cutoff. The recorded pre-fix failures and post-fix passes provide executable checks of those explanations.
4. **A concrete course correction:** The initial targeted rating/playlist checks were incomplete: they used an existing playlist membership or explicit database inserts. An actual POST for a new playlist song then raised a NOT NULL error. Codex traced that back to missing association metadata, added a separate regression and fix, and reran the full HTTP flow. Thus the initial assumption that fixing the five reported service defects was sufficient for the whole workflow was revised based on execution evidence.

All verification above was executed by Codex. No independent student verification or manual debugging conversation is invented here. The saved tests, failure logs, and commit history make the work inspectable.

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


### **Issue #2 — Friends Listening Now shows people from yesterday**

**How you reproduced it:** The new HTTP tests created a friendship from `viewer` to `friend`, inserted a listening event at 23:00 UTC on October 10, 2026, and fixed the feed clock at October 11, 09:00 UTC. Before the fix, `GET /feed/viewer/listening-now` returned that friend even though the event was yesterday. A second case compared a friend who listened at exactly midnight with another who listened at 23:59:59 the previous day: both appeared, instead of only today's listener.

**How you found the root cause:** Starting at `routes/feed.py:listening_now()`, the investigation followed `get_friends_listening_now()` in `services/feed_service.py`, examined `ListeningEvent.listened_at` and the friendships relation in `models.py`, and compared the separate `get_activity_feed()` path. The friend-ID filter and newest-first deduplication explained who appears and which song is shown. The decisive step was calculating `cutoff`: at 09:00 it was yesterday at 09:00, which necessarily includes yesterday at 23:00. Fixed-clock tests confirmed that exact boundary error.

**The root cause:** `cutoff = datetime.now(timezone.utc) - RECENT_THRESHOLD`, with `RECENT_THRESHOLD = timedelta(hours=24)`, defines a rolling 24-hour interval. The requested behavior is a calendar-day interval. A late-night listen therefore stays visible well into the next day even when that friend has not listened today. Changing deduplication would not help because the wrong event already passes the timestamp filter.

**Your fix:** Set the cutoff to today's UTC midnight with `replace(hour=0, minute=0, second=0, microsecond=0)`, remove the unused rolling-window constant/import, and clarify the function's UTC-day contract. UTC follows the app's existing timestamp convention; the model has no user timezone setting. The query retains the inclusive `>=` boundary so a listen at exactly midnight qualifies.

**Your side-effect check:** All four new feed tests passed. They check yesterday at 23:00 and 23:59:59 is excluded, midnight is included, multiple listens yield only the latest song per friend, multiple friends remain sorted newest first, and self/nonfriend events stay excluded. They also cover no friends and a missing user. Crucially, the older listen still appears in `/feed/viewer/activity`, which should retain historical activity. This confirms the narrower cutoff affects only listening-now, without deleting events or filtering the separate activity feed.

**Regression tests:** `tests/test_issue2_feed_regression.py`; both previous-day boundary tests failed before the fix.

### **Issue #3 — The same song keeps showing up twice in search**

**How you reproduced it:** Started the seeded Flask app and requested `/songs/search?q=Anthem` over HTTP. It returned `count: 3` with the same song ID, title, and three tags repeated three times. The original multi-tag search test also failed (`3` instead of `1`). A new API regression created a three-tag song plus a distinct recording with the same title: searching mixed-case `aNtHeM` produced four rows instead of two.

**How you found the root cause:** The investigation followed `routes/songs.py:search()` → `services/search_service.py:search_songs()` → the `select(Song).outerjoin(song_tags, ...)` query. `models.py` confirmed that each song/tag pair is a separate association row and that `Song.tags` is loaded as a relationship for serialization. Inspecting the actual response established that repeated entries shared one primary key; they were not duplicate song records. Comparing zero-, one-, and three-tag fixtures isolated SQL join multiplicity as the trigger.

**The root cause:** The outer join creates one SQL row for each matching song/tag pair. `db.session.execute(...).scalars().all()` retains repeated references to the same `Song` identity in the result sequence. The final list comprehension serializes each reference again. Thus three tags produce three search entries; one tag or no tags produces only one. ORM identity reuse alone does not make a scalar result list unique.

**Your fix:** Added `.unique()` between `.scalars()` and `.all()`. This deduplicates by mapped entity identity before serialization, preserving all distinct songs and their full tag lists. Deduplicating by title would incorrectly merge different recordings with the same title, so the regression explicitly checks that case.

**Your side-effect check:** All five original search tests and the new endpoint regression passed (six tests total). They cover zero and one tag, multiple tags, artist matching, mixed-case title matching, no match, and the missing-query 400 response. The new regression asserts all three tag names remain present and both distinct same-title IDs survive. These checks show that removing duplicate result identities does not discard tags or separate recordings, or change search matching/error behavior.

**Regression tests:** `tests/test_issue3_search_regression.py`; its two-recording case failed with four results before the fix.

### **Issue #4 — I got notified when a friend added my song to a playlist but not when they rated it**

**How you reproduced it:** In an isolated API fixture, `viewer` shared a song and `friend` posted a five-star rating to `/songs/song/rate`. The endpoint returned 201 and the database contained the score, but `/users/viewer/notifications?unread_only=true` returned zero notifications. Updating a rating also produced none. As a control, posting an already-populated playlist membership exercised the existing playlist-notification branch and produced `song_added_to_playlist`. The initial rating tests failed before any service changes.

**How you found the root cause:** Followed `routes/songs.py:rate()` into `services/notification_service.py:rate_song()`, then compared it line by line with `add_to_playlist()` in the same module. Followed that function's `create_notification()` call into `Notification` persistence and checked `routes/users.py:notifications()` → `get_notifications()`. The stored rating proved the write route ran; zero notification rows proved this was not merely a display or unread-filter problem. The decisive structural difference was that the playlist path explicitly invoked the notification helper, while the rating path committed and immediately returned.

**The root cause:** `rate_song()` persisted a `Rating` but never called `create_notification()`. The app has no model event hook, signal, or background worker that automatically turns rating rows into notifications. Therefore a successful rating write could never create the separate `Notification` row that the notifications endpoint queries. Saving the rating and notifying the sharer are two explicit application operations.

**Your fix:** After the successful rating commit, call the existing `create_notification()` helper with recipient `song.shared_by`, type `song_rated`, and a message identifying the rater, song, and score. Apply `song.shared_by != user_id`, matching the playlist path's self-notification guard. Successful updates also notify, because an updated score is another rating interaction; they continue to update the existing unique rating row.

**Your side-effect check:** All four notification regression tests passed. They verify rating persistence, correct recipient/type/message, no notification sent to the rater, marking the notification read, and unread-only filtering. Updating 2 stars to 4 retains one rating ID/row and creates the expected interaction notifications. Self-rating saves successfully without notifying, and out-of-range scores or missing song/user IDs create no notifications. The pre-existing playlist notification branch still works. These checks cover shared helpers and both rating creation/update branches, rather than just endpoint startup.

**Regression tests:** `tests/test_issue4_notification_regression.py`; new-rating and updated-rating notification assertions failed before the fix. The playlist control intentionally used an existing membership to isolate notification behavior from adding a new association row; new playlist insertion is investigated separately below.

### **Issue #5 — The last song in a playlist never shows up**

**How you reproduced it:** The original five-song fixture returned four songs and failed both count and order assertions. Added API tests populated `playlist_entries` explicitly, including the required position/adder fields. For seven ordered entries, `GET /playlists/mix/songs` returned six; a one-song playlist returned zero. The missing final position explains the reported moving-last-item symptom; the append assertions below verify that the fixed version returns both the previously last song and the new one. Direct association inserts isolated the reported retrieval bug from the separate new-song insertion issue noted below.

**How you found the root cause:** Followed `routes/playlists.py:get_songs()` into `services/playlist_service.py:get_playlist_songs()`. Checked `models.py:playlist_entries`, then the service's join, playlist-ID filter, and ascending position sort. The database fixture held every expected row, and the query requested all matching songs. The decisive step was inspecting the final serialization expression: it iterated `songs[:-1]`, dropping one already-retrieved song after the database query. This also explained why the missing song changed after an append.

**The root cause:** Python's slice `songs[:-1]` excludes the last list element. The query orders by ascending position, so the excluded element is precisely the newest/highest-position song. The omission is unconditional: a one-song list becomes empty, and every nonempty playlist loses one item. Returning all playlist songs requires iterating the entire query result, not shortening it before serialization.

**Your fix:** Serialize `songs` directly instead of `songs[:-1]`. The existing query, playlist validation, and order remain unchanged.

**Your side-effect check:** All three original playlist tests and three added parameterized API cases passed (six tests total). The new cases cover empty, one-song, and seven-song playlists, then append another entry and assert it appears last and increases the count. Entries are inserted in reverse order with nonconsecutive positions to ensure the API still orders by stored position. Playlist metadata remains readable, and an unknown playlist still returns 404. This checks both sides of the off-by-one boundary and confirms retrieval order is preserved.

**Regression tests:** `tests/test_issue5_playlist_regression.py`; all three cases failed before the fix, including the empty-start case after its first append.

### Additional defect — Adding a new playlist song violates required metadata

**How you reproduced it:** After the five reported fixes, the end-to-end check posted a song not already in `/playlists/mix/songs`. Two new tests raised SQLite `IntegrityError: NOT NULL constraint failed: playlist_entries.position`; invalid-ID handling still passed. The rating notification control and raw playlist fixtures had not exercised this insertion path. The failure is preserved in `evidence/playlist-add-before.txt`.

**How you found the root cause:** Followed `routes/playlists.py:add_song()` → `notification_service.add_to_playlist()` → `playlist.songs.append(song)`, and compared the emitted insert with `models.py:playlist_entries` and the explicit inserts in `seed_data.py`. The failing SQL supplied playlist/song IDs and the timestamp but omitted the required `position` and `added_by` columns. The seed inserts supplied both, explaining why seeded retrieval worked while adding a new song did not.

**The root cause:** Appending to a plain many-to-many relationship cannot populate custom, nonnullable association metadata automatically. Both `position` and `added_by` require explicit values. This is separate from the retrieval slice in Issue #5 and the missing rating notification in Issue #4.

**Your fix:** Insert into `playlist_entries` explicitly, setting `added_by` to the acting user and `position` to the current maximum position in this playlist plus one (or one for an empty playlist). Using maximum rather than membership count preserves append order when positions contain gaps. The existing membership guard, validation, commit, and notification behavior remain in place.

**Your side-effect check:** All three new addition tests passed. They post two new songs, inspect positions/adder/timestamps, retrieve the complete ordered list, verify sharer notifications, and re-add an existing song without duplicate membership or movement. A gapped playlist at position 10 appends at 11; a self-add does not notify. Invalid playlist/song/user IDs produce 400 responses with no new memberships or notifications. This small classroom app still uses its existing transaction/concurrency model; this change does not add concurrent-writer ordering guarantees.

**Regression tests:** `tests/test_playlist_add_regression.py`. This additional fix has its own commit so the five graded fixes remain independently reviewable.

## Final validation and commit evidence

- **Five reported issues fixed**, each in its own conventional `fix:` commit, plus one separate fix for the additional playlist insertion defect.
- **37 tests passed**: the 13 original tests plus 24 added regression cases. Run `.venv/bin/python -m pytest tests/ -q` after setup; see [final test output](evidence/final-tests.txt).
- Before fixes: the original suite had **4 failed / 9 passed**, and the 21 new issue-specific cases had **10 failed / 11 passed**. The three additional playlist-add cases initially had **2 failed / 1 passed**. These failures are preserved under `evidence/`.
- A real Flask server passed search, listening, feed, rating, notifications, playlist creation, song insertion, and playlist retrieval checks using a disposable SQLite database. Reproduce from the repository root with `PYTHONPATH=. .venv/bin/python scripts/verify_http.py` (port 5056 must be free). See [HTTP smoke output](evidence/live-smoke.txt).
- Python compilation and `git diff --check` passed. Tests were executed with Python 3.10, Flask 3.1.3, Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.0.54, and pytest 9.1.1.
- [Captured commit log](evidence/git-log.txt) and [commit-log screenshot](evidence/commit-history.png). The screenshot shows the actual saved `git log --oneline --decorate` output rendered in a browser, not a simulated terminal.
- [Live branch commit history](https://github.com/Brian-Two/ai201-p5-mixtape-starter/commits/bugfix/mixtape).

### Submission link

https://github.com/Brian-Two/ai201-p5-mixtape-starter/tree/bugfix/mixtape

The branch contains this root-level `submission.md`, all fixes, tests, and evidence. The course-portal submission itself is left to the student.
