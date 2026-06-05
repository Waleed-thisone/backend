import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    String,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_PATH = os.getenv("DATABASE_PATH", "./btc_alert.db")
BOT_TYPES = ("spot_grid", "futures_grid")

DEFAULTS = {
    "spot_grid": {
        "stop_threshold_pct": float(os.getenv("DEFAULT_STOP_THRESHOLD_PCT", "3.0")),
        "restart_threshold_pct": float(os.getenv("DEFAULT_RESTART_THRESHOLD_PCT", "2.0")),
    },
    "futures_grid": {
        "stop_threshold_pct": float(os.getenv("DEFAULT_FUTURES_STOP_THRESHOLD_PCT", "2.0")),
        "restart_threshold_pct": float(os.getenv("DEFAULT_FUTURES_RESTART_THRESHOLD_PCT", "2.0")),
    },
}

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Bot(Base):
    __tablename__ = "bots"

    id = Column(String, primary_key=True)
    bot_type = Column(String, nullable=False, default="spot_grid")
    symbol = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="unknown")
    lower_price = Column(Float, nullable=False, default=0.0)
    upper_price = Column(Float, nullable=False, default=0.0)
    grid_num = Column(Integer, nullable=False, default=0)
    total_profit = Column(Float, nullable=False, default=0.0)
    investment = Column(Float, nullable=False, default=0.0)
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    added_at = Column(String, nullable=False)
    last_synced = Column(String, nullable=True)


class BotTypeSettings(Base):
    __tablename__ = "bot_type_settings"

    bot_type = Column(String, primary_key=True)
    stop_threshold_pct = Column(Float, nullable=False)
    restart_threshold_pct = Column(Float, nullable=False)
    bots_stopped_for_alert = Column(Boolean, nullable=False, default=False)


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_balance = Column(Float, nullable=False)
    timestamp = Column(String, nullable=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bot_to_dict(bot: Bot) -> Dict[str, Any]:
    return {
        "id": bot.id,
        "bot_type": bot.bot_type,
        "symbol": bot.symbol,
        "status": bot.status,
        "lower_price": bot.lower_price,
        "upper_price": bot.upper_price,
        "grid_num": bot.grid_num,
        "total_profit": bot.total_profit,
        "investment": bot.investment,
        "entry_price": bot.entry_price,
        "stop_loss": bot.stop_loss,
        "take_profit": bot.take_profit,
        "added_at": bot.added_at,
        "last_synced": bot.last_synced,
    }


def _settings_to_dict(settings: BotTypeSettings) -> Dict[str, Any]:
    return {
        "stop_threshold_pct": settings.stop_threshold_pct,
        "restart_threshold_pct": settings.restart_threshold_pct,
        "bots_stopped_for_alert": settings.bots_stopped_for_alert,
    }


def _validate_bot_type(bot_type: str) -> str:
    if bot_type not in BOT_TYPES:
        raise ValueError(f"bot_type must be one of: {', '.join(BOT_TYPES)}")
    return bot_type


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _migrate_schema() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("bots")} if inspector.has_table("bots") else set()

    with engine.begin() as conn:
        if inspector.has_table("bots") and "bot_type" not in columns:
            conn.execute(text("ALTER TABLE bots ADD COLUMN bot_type VARCHAR NOT NULL DEFAULT 'spot_grid'"))

        if inspector.has_table("settings") and not inspector.has_table("bot_type_settings"):
            old_settings = conn.execute(
                text(
                    "SELECT stop_threshold_pct, restart_threshold_pct, bots_stopped_for_alert "
                    "FROM settings WHERE id = 1"
                )
            ).fetchone()
            conn.execute(text("DROP TABLE settings"))

            if old_settings is not None:
                DEFAULTS["spot_grid"]["stop_threshold_pct"] = float(old_settings[0])
                DEFAULTS["spot_grid"]["restart_threshold_pct"] = float(old_settings[1])
                DEFAULTS["spot_grid"]["bots_stopped_for_alert"] = bool(old_settings[2])


def init_db() -> None:
    _migrate_schema()
    Base.metadata.create_all(bind=engine)

    with get_session() as session:
        for bot_type in BOT_TYPES:
            settings = session.get(BotTypeSettings, bot_type)
            if settings is None:
                defaults = DEFAULTS[bot_type]
                session.add(
                    BotTypeSettings(
                        bot_type=bot_type,
                        stop_threshold_pct=defaults["stop_threshold_pct"],
                        restart_threshold_pct=defaults["restart_threshold_pct"],
                        bots_stopped_for_alert=defaults.get("bots_stopped_for_alert", False),
                    )
                )


def get_all_bots() -> List[Dict[str, Any]]:
    with get_session() as session:
        bots = session.scalars(select(Bot).order_by(Bot.added_at.desc())).all()
        return [_bot_to_dict(bot) for bot in bots]


def get_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        bot = session.get(Bot, bot_id)
        return _bot_to_dict(bot) if bot else None


def upsert_bot(bot_data: Dict[str, Any]) -> Dict[str, Any]:
    bot_id = str(bot_data["id"])
    bot_type = _validate_bot_type(bot_data.get("bot_type", "spot_grid"))

    with get_session() as session:
        bot = session.get(Bot, bot_id)
        if bot is None:
            bot = Bot(
                id=bot_id,
                bot_type=bot_type,
                added_at=bot_data.get("added_at") or _utc_now(),
            )
            session.add(bot)

        bot.bot_type = bot_data.get("bot_type", bot.bot_type or bot_type)
        bot.symbol = bot_data.get("symbol", bot.symbol or "")
        bot.status = bot_data.get("status", bot.status or "unknown")
        bot.lower_price = float(bot_data.get("lower_price", bot.lower_price or 0.0))
        bot.upper_price = float(bot_data.get("upper_price", bot.upper_price or 0.0))
        bot.grid_num = int(bot_data.get("grid_num", bot.grid_num or 0))
        bot.total_profit = float(bot_data.get("total_profit", bot.total_profit or 0.0))
        bot.investment = float(bot_data.get("investment", bot.investment or 0.0))
        bot.entry_price = bot_data.get("entry_price", bot.entry_price)
        bot.stop_loss = bot_data.get("stop_loss", bot.stop_loss)
        bot.take_profit = bot_data.get("take_profit", bot.take_profit)
        bot.last_synced = bot_data.get("last_synced") or _utc_now()
        session.flush()
        return _bot_to_dict(bot)


def remove_bot_id(bot_id: str) -> None:
    with get_session() as session:
        bot = session.get(Bot, bot_id)
        if bot is None:
            raise KeyError(f"Bot {bot_id} not found")
        session.delete(bot)


def replace_bot_id(old_bot_id: str, new_bot_id: str, bot_data: Dict[str, Any]) -> Dict[str, Any]:
    with get_session() as session:
        old_bot = session.get(Bot, old_bot_id)
        if old_bot is None:
            raise KeyError(f"Bot {old_bot_id} not found")

        added_at = old_bot.added_at
        bot_type = bot_data.get("bot_type", old_bot.bot_type)
        session.delete(old_bot)
        session.flush()

        bot = Bot(
            id=str(new_bot_id),
            bot_type=_validate_bot_type(bot_type),
            symbol=bot_data.get("symbol", ""),
            status=bot_data.get("status", "active"),
            lower_price=float(bot_data.get("lower_price", 0.0)),
            upper_price=float(bot_data.get("upper_price", 0.0)),
            grid_num=int(bot_data.get("grid_num", 0)),
            total_profit=float(bot_data.get("total_profit", 0.0)),
            investment=float(bot_data.get("investment", 0.0)),
            entry_price=bot_data.get("entry_price"),
            stop_loss=bot_data.get("stop_loss"),
            take_profit=bot_data.get("take_profit"),
            added_at=added_at,
            last_synced=bot_data.get("last_synced") or _utc_now(),
        )
        session.add(bot)
        session.flush()
        return _bot_to_dict(bot)


def get_settings() -> Dict[str, Any]:
    with get_session() as session:
        result = {}
        for bot_type in BOT_TYPES:
            settings = session.get(BotTypeSettings, bot_type)
            if settings is None:
                raise RuntimeError(f"Settings missing for {bot_type}; call init_db() first")
            result[bot_type] = _settings_to_dict(settings)
        return result


def get_settings_for_type(bot_type: str) -> Dict[str, Any]:
    bot_type = _validate_bot_type(bot_type)
    with get_session() as session:
        settings = session.get(BotTypeSettings, bot_type)
        if settings is None:
            raise RuntimeError(f"Settings missing for {bot_type}; call init_db() first")
        return _settings_to_dict(settings)


def update_settings(bot_type: str, stop_pct: float, restart_pct: float) -> Dict[str, Any]:
    bot_type = _validate_bot_type(bot_type)
    if bot_type == "spot_grid" and stop_pct <= restart_pct:
        raise ValueError(
            "For spot grid, stop_threshold_pct must be greater than restart_threshold_pct"
        )
    if bot_type == "futures_grid" and restart_pct < stop_pct:
        raise ValueError(
            "For futures grid, restart_threshold_pct must be >= stop_threshold_pct"
        )

    with get_session() as session:
        settings = session.get(BotTypeSettings, bot_type)
        if settings is None:
            raise RuntimeError(f"Settings missing for {bot_type}; call init_db() first")
        settings.stop_threshold_pct = stop_pct
        settings.restart_threshold_pct = restart_pct
        session.flush()
        return get_settings()


def set_bots_stopped_for_alert(bot_type: str, value: bool) -> None:
    bot_type = _validate_bot_type(bot_type)
    with get_session() as session:
        settings = session.get(BotTypeSettings, bot_type)
        if settings is None:
            raise RuntimeError(f"Settings missing for {bot_type}; call init_db() first")
        settings.bots_stopped_for_alert = value


def save_balance_snapshot(balance: float) -> None:
    with get_session() as session:
        session.add(
            BalanceSnapshot(
                total_balance=float(balance),
                timestamp=_utc_now(),
            )
        )
