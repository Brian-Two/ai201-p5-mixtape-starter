from app import db
from models import Rating, Notification, playlist_entries


def test_rating_notifies_sharer_and_supports_read_filter(api):
    response = api.post('/songs/song/rate', json={'user_id': 'friend', 'score': 5})
    assert response.status_code == 201
    assert Rating.query.one().score == 5
    notifications = api.get('/users/viewer/notifications?unread_only=true').json
    assert notifications['count'] == 1
    notification = notifications['notifications'][0]
    assert notification['type'] == 'song_rated'
    assert notification['user_id'] == 'viewer'
    assert 'friend' in notification['body']
    assert 'Crown Heights Anthem' in notification['body']
    assert '5' in notification['body']
    assert api.get('/users/friend/notifications').json['count'] == 0
    assert api.post(f"/users/notifications/{notification['id']}/read").status_code == 200
    assert api.get('/users/viewer/notifications?unread_only=true').json['count'] == 0
    assert api.get('/users/viewer/notifications').json['count'] == 1


def test_rating_update_keeps_single_row_and_notifies_again(api):
    first = api.post('/songs/song/rate', json={'user_id': 'friend', 'score': 2})
    second = api.post('/songs/song/rate', json={'user_id': 'friend', 'score': 4})
    assert first.json['id'] == second.json['id']
    assert Rating.query.count() == 1
    assert Rating.query.one().score == 4
    assert Notification.query.filter_by(notification_type='song_rated').count() == 2


def test_self_rating_and_invalid_requests_do_not_notify(api):
    assert api.post('/songs/song/rate', json={'user_id': 'viewer', 'score': 3}).status_code == 201
    for song, user, score in [('song', 'friend', 0), ('song', 'friend', 6),
                              ('missing', 'friend', 5), ('song', 'missing', 5)]:
        assert api.post(f'/songs/{song}/rate', json={'user_id': user, 'score': score}).status_code == 400
    assert Rating.query.count() == 1
    assert Notification.query.count() == 0


def test_existing_playlist_notification_path(api):
    # Use a populated membership to isolate the pre-existing notification path.
    db.session.execute(playlist_entries.insert().values(
        playlist_id='mix', song_id='song', position=1, added_by='friend'))
    db.session.commit()
    assert api.post('/playlists/mix/songs', json={'song_id': 'song', 'added_by': 'friend'}).status_code == 201
    notification = Notification.query.one()
    assert notification.notification_type == 'song_added_to_playlist'
    assert notification.user_id == 'viewer'
