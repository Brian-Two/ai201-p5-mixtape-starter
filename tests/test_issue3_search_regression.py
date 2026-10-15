from app import db
from models import Song, Tag


def test_multitag_match_is_unique_and_keeps_all_tags(api):
    song = db.session.get(Song, 'song')
    song.tags = [Tag(name=name) for name in ('rap', 'hip-hop', 'boom bap')]
    # A distinct recording with the same title must not be collapsed by title.
    db.session.add(Song(id='second-recording', title=song.title, artist='Cover Band', shared_by='viewer'))
    db.session.commit()
    response = api.get('/songs/search?q=aNtHeM')
    assert response.status_code == 200
    assert response.json['count'] == 2
    assert {row['id'] for row in response.json['results']} == {'song', 'second-recording'}
    result = next(row for row in response.json['results'] if row['id'] == 'song')
    assert set(result['tags']) == {'rap', 'hip-hop', 'boom bap'}
    artist_results = api.get('/songs/search?q=borough').json
    assert artist_results['count'] == 1
    assert artist_results['results'][0]['id'] == 'song'
    assert api.get('/songs/search?q=NoSuchSong').json['count'] == 0
    assert api.get('/songs/search').status_code == 400
