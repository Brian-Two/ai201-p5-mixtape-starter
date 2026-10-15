"""Small, isolated HTTP fixtures for the added regression tests."""
import pytest
from app import create_app, db
from models import User, Song, Playlist


@pytest.fixture
def api():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        db.session.add_all([
            User(id=name, username=name, email=f'{name}@example.com')
            for name in ('viewer', 'friend', 'outsider')
        ])
        db.session.flush()
        db.session.add_all([
            Song(id='song', title='Crown Heights Anthem', artist='Borough Kings', shared_by='viewer'),
            Song(id='other', title='Other Track', artist='Other Artist', shared_by='viewer'),
            Playlist(id='mix', name='Friday Energy', created_by='friend'),
        ])
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.drop_all()
