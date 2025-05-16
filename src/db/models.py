# src/db/models.py

from datetime import datetime, time as dt_time # Додаємо time як dt_time для ясності
from typing import Optional, List # List може знадобитися для relationships в майбутньому

from sqlalchemy import BigInteger, String, TIMESTAMP, func, Boolean, Time, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Імпортуємо базовий клас для моделей з нашого модуля database
from .database import Base

# Визначимо можливі значення для сервісів, щоб використовувати їх як Enum або константи пізніше
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

    # Поля для налаштувань сервісів
    preferred_weather_service: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=ServiceChoice.OPENWEATHERMAP, server_default=ServiceChoice.OPENWEATHERMAP
    )
    preferred_alert_service: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=ServiceChoice.UKRAINEALARM, server_default=ServiceChoice.UKRAINEALARM
    )
    
    # Нові поля для нагадувань про погоду
    weather_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default='false'
    )
    # Зберігаємо час як об'єкт datetime.time. SQLAlchemy підтримує тип Time.
    # `timezone=False` для Time, оскільки ми зазвичай хочемо зберігати "локальний" час нагадування (наприклад, 07:00)
    # без прив'язки до часового поясу в самій БД для цього конкретного поля.
    # Логіка часових поясів (якщо потрібна) буде оброблятися в коді.
    weather_reminder_time: Mapped[Optional[dt_time]] = mapped_column( # Використовуємо dt_time
        Time(timezone=False), nullable=True
    )
    # Якщо б ми хотіли зберігати час як рядок "HH:MM":
    # weather_reminder_time_str: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)


    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Приклад, якщо б ми мали окрему таблицю для налаштувань нагадувань (поки не використовуємо)
    # weather_reminder_settings: Mapped[List["WeatherReminderSetting"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        reminder_time_str = self.weather_reminder_time.strftime('%H:%M') if self.weather_reminder_time else "None"
        return (f"<User(user_id={self.user_id}, username='{self.username}', "
                f"pref_city='{self.preferred_city}', "
                f"weather_service='{self.preferred_weather_service}', alert_service='{self.preferred_alert_service}', "
                f"weather_reminder_enabled={self.weather_reminder_enabled}, weather_reminder_time='{reminder_time_str}')>")

# Приклад окремої таблиці для нагадувань (якщо б знадобилося багато нагадувань на користувача)
# Ми поки що не використовуємо цей підхід, а додаємо поля до User.
# class WeatherReminderSetting(Base):
#     __tablename__ = "weather_reminder_settings"
#     id: Mapped[int] = mapped_column(primary_key=True, index=True)
#     user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
#     reminder_time: Mapped[dt_time] = mapped_column(Time(timezone=False))
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
#     days_of_week: Mapped[Optional[str]] = mapped_column(String(20), nullable=True) # наприклад, "1,2,3,4,5" або "mon,tue"
#     forecast_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # "current", "daily_summary"
    
#     user: Mapped["User"] = relationship(back_populates="weather_reminder_settings")

#     def __repr__(self) -> str:
#         return f"<WeatherReminderSetting(id={self.id}, user_id={self.user_id}, time='{self.reminder_time.strftime('%H:%M')}', active={self.is_active})>"