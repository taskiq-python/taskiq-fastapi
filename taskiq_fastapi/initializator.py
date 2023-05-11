from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from starlette.requests import HTTPConnection
from taskiq import AsyncBroker, TaskiqEvents, TaskiqState
from taskiq.cli.utils import import_object


def startup_event_generator(app: FastAPI) -> Callable[[TaskiqState], Awaitable[None]]:
    """
    Generate shutdown event.

    This function takes FastAPI application
    and runs startup event on broker's startup.

    :param app: fastapi application.
    :returns: startup handler.
    """

    async def startup(state: TaskiqState) -> None:
        state.fastapi_app = app
        app.router.routes = []
        await app.router.startup()

    return startup


def shutdown_event_generator(app: FastAPI) -> Callable[[TaskiqState], Awaitable[None]]:
    """
    Generate shutdown event.

    This function takes FastAPI application
    and runs shutdown event on broker's shutdown.

    :param app: current application.
    :return: startup event handler.
    """

    async def startup(_: TaskiqState) -> None:
        await app.router.shutdown()

    return startup


def init(broker: AsyncBroker, app_path: str) -> None:
    """
    Add taskiq startup events.

    This is the main function to integrate FastAPI
    with taskiq.

    This function imports fastapi application by
    python's path string and adds startup events
    for broker.

    :param broker: current broker to use.
    :param app_path: path to fastapi application.
    :raises ValueError: if fastapi cannot be resolved.
    """
    if not broker.is_worker_process:
        return

    app = import_object(app_path)

    if not isinstance(app, FastAPI):
        app = app()

    if not isinstance(app, FastAPI):
        raise ValueError(f"'{app_path}' is not a FastAPI application.")

    populate_dependency_context(broker, app)

    broker.add_event_handler(
        TaskiqEvents.WORKER_STARTUP,
        startup_event_generator(app),
    )

    broker.add_event_handler(
        TaskiqEvents.WORKER_SHUTDOWN,
        shutdown_event_generator(app),
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
