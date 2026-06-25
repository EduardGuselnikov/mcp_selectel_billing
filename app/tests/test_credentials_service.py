from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, UserSelectelCredentials
from app.services import credentials_service


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def test_bootstrap_credentials_from_env_creates_new_record(monkeypatch) -> None:
    monkeypatch.setattr(credentials_service.settings, "default_user_id", "default")
    monkeypatch.setattr(credentials_service.settings, "selectel_account_id", "56325")
    monkeypatch.setattr(credentials_service.settings, "selectel_service_user_name", "Becky")
    monkeypatch.setattr(
        credentials_service.settings,
        "selectel_service_user_password",
        "secret",
    )

    db = _make_session()
    assert credentials_service.bootstrap_credentials_from_env(db) is True

    stored = db.query(UserSelectelCredentials).filter_by(user_id="default").one()
    assert stored.selectel_account_id == "56325"
    assert stored.service_user_name == "Becky"


def test_bootstrap_credentials_from_env_updates_changed_account(monkeypatch) -> None:
    monkeypatch.setattr(credentials_service.settings, "default_user_id", "default")
    monkeypatch.setattr(credentials_service.settings, "selectel_account_id", "56325")
    monkeypatch.setattr(credentials_service.settings, "selectel_service_user_name", "Becky")
    monkeypatch.setattr(
        credentials_service.settings,
        "selectel_service_user_password",
        "secret",
    )

    db = _make_session()
    db.add(
        UserSelectelCredentials(
            user_id="default",
            selectel_account_id="247165",
            service_user_name="Justine",
            service_user_password="old-secret",
            selectel_token="cached-token",
        )
    )
    db.commit()

    assert credentials_service.bootstrap_credentials_from_env(db) is True

    stored = db.query(UserSelectelCredentials).filter_by(user_id="default").one()
    assert stored.selectel_account_id == "56325"
    assert stored.service_user_name == "Becky"
    assert stored.service_user_password == "secret"
    assert stored.selectel_token is None


def test_bootstrap_credentials_from_env_skips_unchanged_values(monkeypatch) -> None:
    monkeypatch.setattr(credentials_service.settings, "default_user_id", "default")
    monkeypatch.setattr(credentials_service.settings, "selectel_account_id", "56325")
    monkeypatch.setattr(credentials_service.settings, "selectel_service_user_name", "Becky")
    monkeypatch.setattr(
        credentials_service.settings,
        "selectel_service_user_password",
        "secret",
    )

    db = _make_session()
    db.add(
        UserSelectelCredentials(
            user_id="default",
            selectel_account_id="56325",
            service_user_name="Becky",
            service_user_password="secret",
        )
    )
    db.commit()

    assert credentials_service.bootstrap_credentials_from_env(db) is False
