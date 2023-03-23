from typing import Callable, Union
from fastapi import FastAPI, Request
from taskiq import AsyncBroker, TaskiqEvents, TaskiqState


def startup_event_generator(app: FastAPI, with_dependencies: bool):
    async def startup(state: TaskiqState):
        await app.router.startup()

    return startup


def shutdown_event_generator(app: FastAPI):
    async def startup(state: TaskiqState):
        await app.router.shutdown()

    return startup


def init(
    broker: AsyncBroker,
    app: Union[FastAPI, Callable[[], FastAPI]],
    factory: bool = False,
) -> None:
    if not broker.is_worker_process:
        return

    if factory:
        app = app()

    broker.add_dependency_context({Request: Request({"app": app, "type": "http"})})

    broker.add_event_handler(
        TaskiqEvents.WORKER_STARTUP,
        startup_event_generator(app),
    )

    broker.add_event_handler(
        TaskiqEvents.WORKER_SHUTDOWN,
        shutdown_event_generator(app),
    )
