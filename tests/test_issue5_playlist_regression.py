import pytest
from app import db
from models import Song, playlist_entries


@pytest.mark.parametrize('size', [0, 1, 7])
def test_playlist_returns_every_position_in_order(api, size):
    for i in range(size):
        db.session.add(Song(id=f'track-{i}', title=f'Track {i}', artist='DJ', shared_by='viewer'))
    db.session.flush()
    # Insert backwards and with gaps: retrieval must use position, not insertion/count.
    for i in reversed(range(size)):
        db.session.execute(playlist_entries.insert().values(
            playlist_id='mix', song_id=f'track-{i}', position=(i + 1) * 10, added_by='friend'))
    db.session.commit()
    response = api.get('/playlists/mix/songs')
    assert response.status_code == 200
    assert response.json['count'] == size
    assert [song['id'] for song in response.json['songs']] == [f'track-{i}' for i in range(size)]
    # Reproduce the reported moving-last-item symptom with an eighth/new entry.
    db.session.execute(playlist_entries.insert().values(
        playlist_id='mix', song_id='other', position=(size + 1) * 10, added_by='friend'))
    db.session.commit()
    response = api.get('/playlists/mix/songs').json
    assert response['count'] == size + 1
    assert response['songs'][-1]['id'] == 'other'
    assert api.get('/playlists/mix').json['name'] == 'Friday Energy'
    assert api.get('/playlists/missing/songs').status_code == 404
