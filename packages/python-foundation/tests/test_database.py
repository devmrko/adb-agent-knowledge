import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from example_app.models import Project
from python_foundation.database import SqlAlchemyUnitOfWork, sessions


def test_commit_and_multi_write_rollback(application):
    factory = sessions(application.state.engine)
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.add(Project(id="committed", name="Keep", version=0))
    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.add_all(
            [Project(id="one", name="One", version=0), Project(id="two", name="Two", version=0)]
        )
        uow.session.flush()
        raise RuntimeError("rollback")
    with factory() as session:
        assert list(session.scalars(select(Project.id))) == ["committed"]


def test_commit_failure_rolls_back_and_returns_connection(application):
    factory = sessions(application.state.engine)
    with pytest.raises(IntegrityError), SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.add(Project(id="bad", name=None, version=0))
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.add(Project(id="good", name="Works after failure", version=0))
    assert application.state.engine.pool.checkedout() == 0


def test_read_only_rejects_flush_and_uow_cannot_be_reentered(application):
    factory = sessions(application.state.engine)
    uow = SqlAlchemyUnitOfWork(factory, read_only=True)
    with pytest.raises(RuntimeError, match="read-only"), uow:
        uow.session.add(Project(name="Forbidden"))
        uow.session.flush()
    with pytest.raises(RuntimeError, match="single-use"), uow:
        pass
    assert application.state.engine.pool.checkedout() == 0


def test_concurrent_orm_version_conflict(application):
    from sqlalchemy.orm.exc import StaleDataError

    factory = sessions(application.state.engine)
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.add(Project(id="versioned", name="initial", version=0))
    with factory() as first, factory() as second:
        one, two = first.get(Project, "versioned"), second.get(Project, "versioned")
        one.name = "one"
        first.commit()
        two.name = "two"
        with pytest.raises(StaleDataError):
            second.commit()
        second.rollback()
