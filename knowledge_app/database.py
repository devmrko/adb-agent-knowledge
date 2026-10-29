from pathlib import Path
from typing import Any

from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from knowledge_app.settings import ROOT, Settings
from python_foundation.database import create_database
from python_foundation.settings import FoundationSettings


def database(settings: Settings) -> Engine:
    if settings.database_url.startswith("sqlite"):
        return create_database(FoundationSettings(database_url=SecretStr(settings.database_url)))
    required = {
        "USER_NAME": settings.user_name,
        "USER_PASSWORD": settings.user_password.get_secret_value(),
        "WALLET_DIR": settings.wallet_dir,
        "ORACLE_DSN": settings.oracle_dsn,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError("Missing Oracle configuration: " + ", ".join(missing))
    wallet = Path(settings.wallet_dir).expanduser()
    if not wallet.is_absolute():
        wallet = ROOT / wallet
    if not (wallet / "tnsnames.ora").is_file() or not (wallet / "ewallet.pem").is_file():
        raise ValueError("WALLET_DIR must contain extracted tnsnames.ora and ewallet.pem")
    args: dict[str, Any] = dict(
        user=settings.user_name,
        password=settings.user_password.get_secret_value(),
        dsn=settings.oracle_dsn,
        config_dir=str(wallet),
        wallet_location=str(wallet),
        tcp_connect_timeout=10,
        retry_count=0,
    )
    if settings.wallet_password:
        args["wallet_password"] = settings.wallet_password.get_secret_value()
    engine = create_engine(
        "oracle+oracledb://",
        connect_args=args,
        pool_size=3,
        max_overflow=0,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def use_utc(dbapi_connection: Any, connection_record: Any) -> None:
        # Oracle interprets timestamp bind values in the session timezone.
        # All application timestamps use UTC, including outbox availability.
        with dbapi_connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET TIME_ZONE = '+00:00'")

    return engine
