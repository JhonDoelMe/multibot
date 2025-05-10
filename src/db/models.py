# src/db/models.py

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

# Импортируем базовый класс для моделей из нашего модуля database
from .database import Base

# Определим возможные значения для сервисов, чтобы использовать их как Enum или константы позже
class ServiceChoice:
    OPENWEATHERMAP = "owm"
    WEATHERAPI = "wapi"
    UKRAINEALARM = "ualarm"
    ALERTSINUA = "ainua"

class User(Base):
    """
    Модель пользователя Telegram, хранящаяся в базе данных.
    """
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    preferred_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Новые поля для настроек сервисов
    preferred_weather_service: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=ServiceChoice.OPENWEATHERMAP)
    preferred_alert_service: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=ServiceChoice.UKRAINEALARM)
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (f"<User(user_id={self.user_id}, username='{self.username}', "
                f"weather_service='{self.preferred_weather_service}', alert_service='{self.preferred_alert_service}')>")