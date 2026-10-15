from datetime import datetime, timezone
from unittest.mock import patch
from app import db
from models import ListeningEvent, friendships

NOW = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)


def add_event(user, day, hour, minute=0, song='song', second=0):
    db.session.add(ListeningEvent(user_id=user, song_id=song,
        listened_at=datetime(2026, 10, day, hour, minute, second, tzinfo=timezone.utc)))


def befriend(user):
    db.session.execute(friendships.insert().values(user_id='viewer', friend_id=user))


def test_previous_night_excluded_but_activity_retained(api):
    befriend('friend')
    add_event('friend', 10, 23)
    db.session.commit()
    with patch('services.feed_service.datetime') as clock:
        clock.now.return_value = NOW
        response = api.get('/feed/viewer/listening-now')
        assert response.status_code == 200
        assert response.json == {'count': 0, 'feed': []}
    activity = api.get('/feed/viewer/activity').json
    assert activity['count'] == 1
    assert activity['feed'][0]['friend']['id'] == 'friend'


def test_midnight_included_yesterday_last_second_excluded(api):
    befriend('friend')
    befriend('outsider')
    add_event('friend', 11, 0)
    add_event('outsider', 10, 23, 59, second=59)
    db.session.commit()
    with patch('services.feed_service.datetime') as clock:
        clock.now.return_value = NOW
        feed = api.get('/feed/viewer/listening-now').json['feed']
    assert [item['friend']['id'] for item in feed] == ['friend']


def test_latest_per_friend_order_and_nonfriends(api):
    befriend('friend')
    add_event('friend', 11, 0)
    add_event('friend', 11, 8, song='other')
    add_event('outsider', 11, 8, 30)
    add_event('viewer', 11, 8, 45)
    db.session.commit()
    with patch('services.feed_service.datetime') as clock:
        clock.now.return_value = NOW
        feed = api.get('/feed/viewer/listening-now').json['feed']
    assert len(feed) == 1
    assert feed[0]['friend']['id'] == 'friend'
    assert feed[0]['song']['id'] == 'other'
    befriend('outsider')
    db.session.commit()
    with patch('services.feed_service.datetime') as clock:
        clock.now.return_value = NOW
        feed = api.get('/feed/viewer/listening-now').json['feed']
    assert [item['friend']['id'] for item in feed] == ['outsider', 'friend']


def test_no_friends_and_unknown_user(api):
    assert api.get('/feed/viewer/listening-now').json == {'count': 0, 'feed': []}
    assert api.get('/feed/missing/listening-now').status_code == 404
