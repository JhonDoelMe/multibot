# src/db/models.py

from datetime import datetime, time as dt_time 
from typing import Optional, List 

from sqlalchemy import BigInteger, String, TIMESTAMP, func, Boolean, Time, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

class ServiceChoice:
    OPENWEATHERMAP = "owm"
    WEATHERAPI = "wapi"
    UKRAINEALARM = "ualarm"
    ALERTSINUA = "ainua"

class User(Base):
    """
    Модель користувача Telegram, що зберігається в базі даних.
    """
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    preferred_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    preferred_weather_service: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=ServiceChoice.OPENWEATHERMAP, server_default=ServiceChoice.OPENWEATHERMAP
    )
    preferred_alert_service: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=ServiceChoice.UKRAINEALARM, server_default=ServiceChoice.UKRAINEALARM
    )
    
    weather_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default='false'
    )
    weather_reminder_time: Mapped[Optional[dt_time]] = mapped_column(
        Time(timezone=False), nullable=True
    )

    is_blocked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default='false'
    ) # <--- ПОЛЕ ДЛЯ БЛОКУВАННЯ

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        reminder_time_str = self.weather_reminder_time.strftime('%H:%M') if self.weather_reminder_time else "None"
        return (f"<User(user_id={self.user_id}, username='{self.username}', "
                f"pref_city='{self.preferred_city}', "
                f"weather_service='{self.preferred_weather_service}', alert_service='{self.preferred_alert_service}', "
                f"weather_reminder_enabled={self.weather_reminder_enabled}, weather_reminder_time='{reminder_time_str}', "
                f"is_blocked={self.is_blocked})>")

