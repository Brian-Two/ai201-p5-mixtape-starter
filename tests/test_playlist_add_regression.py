"""Additional starter defect exposed while checking Issues #4 and #5 end to end."""
from app import db
from models import Notification, playlist_entries


def test_add_new_songs_sets_membership_metadata_and_preserves_order(api):
    for song in ('song', 'other'):
        response = api.post('/playlists/mix/songs', json={'song_id': song, 'added_by': 'friend'})
        assert response.status_code == 201
    entries = db.session.execute(db.select(playlist_entries).order_by(playlist_entries.c.position)).mappings().all()
    assert [row['position'] for row in entries] == [1, 2]
    assert [row['added_by'] for row in entries] == ['friend', 'friend']
    assert all(row['added_at'] is not None for row in entries)
    songs = api.get('/playlists/mix/songs').json
    assert [song['id'] for song in songs['songs']] == ['song', 'other']
    assert songs['count'] == 2
    assert Notification.query.filter_by(user_id='viewer', notification_type='song_added_to_playlist').count() == 2
    # Adding an existing song must not duplicate its membership or move it.
    assert api.post('/playlists/mix/songs', json={'song_id': 'song', 'added_by': 'friend'}).status_code == 201
    assert api.get('/playlists/mix/songs').json == songs


def test_append_uses_max_position_and_self_add_does_not_notify(api):
    db.session.execute(playlist_entries.insert().values(
        playlist_id='mix', song_id='song', position=10, added_by='friend'))
    db.session.commit()
    assert api.post('/playlists/mix/songs', json={'song_id': 'other', 'added_by': 'viewer'}).status_code == 201
    row = db.session.execute(db.select(playlist_entries).where(playlist_entries.c.song_id == 'other')).mappings().one()
    assert row['position'] == 11
    assert row['added_by'] == 'viewer'
    assert Notification.query.count() == 0
    assert [song['id'] for song in api.get('/playlists/mix/songs').json['songs']] == ['song', 'other']


def test_invalid_adds_leave_memberships_and_notifications_unchanged(api):
    for playlist, song, user in [('missing', 'song', 'friend'), ('mix', 'missing', 'friend'), ('mix', 'song', 'missing')]:
        assert api.post(f'/playlists/{playlist}/songs', json={'song_id': song, 'added_by': user}).status_code == 400
    assert db.session.execute(db.select(playlist_entries)).all() == []
    assert Notification.query.count() == 0
