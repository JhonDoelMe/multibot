# src/db/models.py

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, String, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

# Импортируем базовый класс для моделей из нашего модуля database
from .database import Base

class User(Base):
    """
    Модель пользователя Telegram, хранящаяся в базе данных.
    """
    __tablename__ = "users"

    # Telegram User ID - первичный ключ
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # Telegram username (может отсутствовать)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Имя пользователя Telegram (обязательно)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Фамилия пользователя Telegram (может отсутствовать)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Предпочитаемый город для погоды (будем использовать в модуле weather)
    preferred_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Дата и время создания записи (автоматически устанавливается БД)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    # Дата и время последнего обновления записи (автоматически обновляется БД)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username={self.username}, first_name={self.first_name})>"

# !!! Важно: Импортируйте все модели здесь, чтобы Alembic или Base.metadata их увидел.
# Если добавите другие модели (например, History), импортируйте их тут же.
# from .models_history import History # Пример импорта другой модели