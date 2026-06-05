from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


BotType = Literal["spot_grid", "futures_grid"]


class BotTypeSettingsModel(BaseModel):
    stop_threshold_pct: float
    restart_threshold_pct: float
    bots_stopped_for_alert: bool = False


class BotAddRequest(BaseModel):
    bot_id: str = Field(min_length=1)
    bot_type: BotType = "spot_grid"


class SettingsUpdateRequest(BaseModel):
    bot_type: BotType
    stop_threshold_pct: float = Field(gt=0, le=100)
    restart_threshold_pct: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.bot_type == "spot_grid" and self.restart_threshold_pct >= self.stop_threshold_pct:
            raise ValueError(
                "For spot grid, restart_threshold_pct must be less than stop_threshold_pct"
            )
        if self.bot_type == "futures_grid" and self.restart_threshold_pct < self.stop_threshold_pct:
            raise ValueError(
                "For futures grid, restart_threshold_pct must be >= stop_threshold_pct"
            )
        return self


class BotResponse(BaseModel):
    id: str
    bot_type: BotType
    symbol: str
    status: str
    lower_price: float
    upper_price: float
    grid_num: int
    total_profit: float
    investment: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    added_at: str
    last_synced: Optional[str] = None


class BotsListResponse(BaseModel):
    bots: List[BotResponse]


class AvailableBotResponse(BaseModel):
    id: str
    bot_type: BotType
    symbol: str
    status: str
    lower_price: float
    upper_price: float
    grid_num: int
    total_profit: float
    investment: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    in_watchlist: bool = False


class AvailableBotsListResponse(BaseModel):
    bots: List[AvailableBotResponse]


class BalanceResponse(BaseModel):
    total_balance: float
    currency: str = "USDT"


class SettingsResponse(BaseModel):
    spot_grid: BotTypeSettingsModel
    futures_grid: BotTypeSettingsModel


class MessageResponse(BaseModel):
    message: str
