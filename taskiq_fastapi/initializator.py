from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from starlette.requests import HTTPConnection
from taskiq import AsyncBroker, TaskiqEvents, TaskiqState
from taskiq.cli.utils import import_object


def startup_event_generator(
    broker: AsyncBroker,
    app_path: str,
) -> Callable[[TaskiqState], Awaitable[None]]:
    """
    Generate shutdown event.

    This function takes FastAPI application path
    and runs startup event on broker's startup.

    :param broker: current broker.
    :param app_path: fastapi application path.
    :returns: startup handler.
    """

    async def startup(state: TaskiqState) -> None:
        if not broker.is_worker_process:
            return
        app = import_object(app_path)
        if not isinstance(app, FastAPI):
            app = app()

        if not isinstance(app, FastAPI):
            raise ValueError(f"'{app_path}' is not a FastAPI application.")

        state.fastapi_app = app
        await app.router.startup()
        state.lf_ctx = app.router.lifespan_context(app)
        await state.lf_ctx.__aenter__()
        populate_dependency_context(broker, app)

    return startup


def shutdown_event_generator(
    broker: AsyncBroker,
) -> Callable[[TaskiqState], Awaitable[None]]:
    """
    Generate shutdown event.

    This function takes FastAPI application
    and runs shutdown event on broker's shutdown.

    :param broker: current broker.
    :return: shutdown event handler.
    """

    async def shutdown(state: TaskiqState) -> None:
        if not broker.is_worker_process:
            return
        await state.fastapi_app.router.shutdown()
        await state.lf_ctx.__aexit__(None, None, None)

    return shutdown


def init(broker: AsyncBroker, app_path: str) -> None:
    """
    Add taskiq startup events.

    This is the main function to integrate FastAPI
    with taskiq.

    It creates startup events for broker. So
    in worker processes all fastapi
    startup events will run.

    :param broker: current broker to use.
    :param app_path: path to fastapi application.
    """
    broker.add_event_handler(
        TaskiqEvents.WORKER_STARTUP,
        startup_event_generator(broker, app_path),
    )

    broker.add_event_handler(
        TaskiqEvents.WORKER_SHUTDOWN,
        shutdown_event_generator(broker),
    )


def populate_dependency_context(broker: AsyncBroker, app: FastAPI) -> None:
    """
    Populate dependency context.

    This function injects the Request and HTTPConnection
    into the broker's dependency context.

    It may be need to be called manually if you are using InMemoryBroker.

    :param broker: current broker to use.
    :param app: current application.
    """
    scope = {"app": app, "type": "http"}

    broker.add_dependency_context(
        {
            Request: Request(scope=scope),
            HTTPConnection: HTTPConnection(scope=scope),
        },
    )
