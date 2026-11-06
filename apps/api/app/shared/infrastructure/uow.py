from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.shared.infrastructure.database import SessionLocal


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal):
        self._session_factory = session_factory
        self.session: Session

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()

    def flush(self) -> None:
        self.session.flush()


def uow_factory() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork()
