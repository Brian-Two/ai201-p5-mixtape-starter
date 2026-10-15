from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from app import db
from models import User, ListeningEvent


@pytest.mark.parametrize('day', range(7))
def test_listen_increments_on_every_consecutive_weekday(api, day):
    now = datetime(2026, 10, 5, 9, tzinfo=timezone.utc) + timedelta(days=day)
    user = db.session.get(User, 'friend')
    user.listening_streak = 12
    user.last_listened_at = now - timedelta(days=1)
    db.session.commit()
    with patch('services.streak_service.datetime') as clock:
        clock.now.return_value = now
        response = api.post('/songs/song/listen', json={'user_id': 'friend'})
        assert response.status_code == 201
        assert api.get('/users/friend/streak').json['streak'] == 13
        # Another listen today still records an event, but cannot inflate the streak.
        api.post('/songs/other/listen', json={'user_id': 'friend'})
        assert api.get('/users/friend/streak').json['streak'] == 13
    assert ListeningEvent.query.filter_by(user_id='friend').count() == 2


@pytest.mark.parametrize('now', [
    datetime(2026, 11, 1, 0, tzinfo=timezone.utc),
    datetime(2027, 1, 1, 0, tzinfo=timezone.utc),
])
def test_calendar_rollover_and_naive_database_timestamp(api, now):
    user = db.session.get(User, 'friend')
    user.listening_streak = 12
    user.last_listened_at = (now - timedelta(minutes=1)).replace(tzinfo=None)
    db.session.commit()
    with patch('services.streak_service.datetime') as clock:
        clock.now.return_value = now
        api.post('/songs/song/listen', json={'user_id': 'friend'})
    assert api.get('/users/friend/streak').json['streak'] == 13
