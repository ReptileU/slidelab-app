from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("postgresql"):
        # Облачная база (Neon) засыпает через ~5 минут простоя и молча рвёт соединения.
        # Без этих настроек запрос на «мёртвом» соединении висит бесконечно — заказ «крутится» и не создаётся.
        return create_async_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=180,  # соединение старше 3 минут не берём — открываем новое
            pool_timeout=20,
            connect_args={"timeout": 20, "command_timeout": 40},
        )
    return create_async_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
