import json, os, subprocess, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from app import create_app, db
from models import User, Song, Tag, ListeningEvent, friendships

repo = Path.cwd()
with tempfile.TemporaryDirectory(prefix='mixtape-smoke-') as directory:
    database = 'sqlite:///' + directory + '/smoke.db'
    app = create_app({'SQLALCHEMY_DATABASE_URI': database})
    now = datetime.now(timezone.utc)
    with app.app_context():
        db.session.add_all([
            User(id='owner', username='owner', email='owner@example.com'),
            User(id='friend', username='friend', email='friend@example.com', listening_streak=12,
                 last_listened_at=now-timedelta(days=1)),
        ])
        db.session.flush()
        song = Song(id='song', title='Anthem', artist='Artist', shared_by='owner')
        song.tags = [Tag(name=name) for name in ('rap', 'soul', 'jazz')]
        db.session.add(song)
        db.session.flush()
        db.session.execute(friendships.insert().values(user_id='owner', friend_id='friend'))
        db.session.add(ListeningEvent(user_id='friend', song_id='song',
            listened_at=now.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(seconds=1)))
        db.session.commit()
    env = dict(os.environ, DATABASE_URL=database)
    with open(repo / 'evidence/live-server.txt', 'w') as log:
        process = subprocess.Popen([str(repo/'.venv/bin/flask'), '--app', 'app:create_app', 'run',
                                   '--host', '127.0.0.1', '--port', '5056'], env=env, stdout=log, stderr=log)
        try:
            def call(path, data=None):
                request = Request('http://127.0.0.1:5056'+path,
                    data=json.dumps(data).encode() if data is not None else None,
                    headers={'Content-Type': 'application/json'})
                with urlopen(request, timeout=3) as response:
                    return response.status, json.load(response)
            for attempt in range(50):
                try:
                    status, search = call('/songs/search?q=Anthem')
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError('Flask exited before smoke check')
                    time.sleep(.1)
            else:
                raise RuntimeError('Flask did not become ready')
            assert status == 200 and search['count'] == 1
            assert set(search['results'][0]['tags']) == {'rap', 'soul', 'jazz'}
            assert call('/feed/owner/listening-now')[1]['count'] == 0
            assert call('/feed/owner/activity')[1]['count'] == 1
            assert call('/songs/song/listen', {'user_id':'friend'})[0] == 201
            assert call('/users/friend/streak')[1]['streak'] == 13
            assert call('/feed/owner/listening-now')[1]['count'] == 1
            assert call('/songs/song/rate', {'user_id':'friend','score':5})[0] == 201
            status, playlist = call('/playlists/', {'name':'Smoke Mix','created_by':'friend'})
            assert status == 201
            assert call('/playlists/'+playlist['id']+'/songs', {'song_id':'song','added_by':'friend'})[0] == 201
            songs = call('/playlists/'+playlist['id']+'/songs')[1]
            assert songs['count'] == 1 and songs['songs'][0]['id'] == 'song'
            notifications = call('/users/owner/notifications')[1]
            assert {n['type'] for n in notifications['notifications']} == {'song_rated','song_added_to_playlist'}
            print('PASS: real Flask HTTP server on 127.0.0.1:5056, disposable SQLite database')
            print('PASS: unique three-tag search; yesterday excluded from listening-now but retained in activity')
            print('PASS: listen saved; streak 12 -> 13; current listen appears in feed')
            print('PASS: rating and playlist-add notifications persisted for song owner')
            print('PASS: create playlist -> add new song -> retrieve its final/only song')
        finally:
            process.terminate()
            process.wait(timeout=5)
