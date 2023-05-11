# Taskiq + FastAPI

This repository has a code to integrate FastAPI with taskiq easily.

Taskiq and FastAPI both have dependencies and this library makes it possible to depend on
`fastapi.Request` or `starlette.requests.HTTPConnection` in taskiq tasks.

With this library you can easily re-use your fastapi dependencies in taskiq functions.

## How does it work?

It adds startup functions to broker so it imports your fastapi application
and creates a single worker-wide Request and HTTPConnection objects that you depend on.

THIS REQUEST IS NOT RELATED TO THE ACTUAL REQUESTS IN FASTAPI!
This request won't have actual data about the request you were handling while sending task.

## Usage

Here we have an example of function that is being used by both taskiq's task and
fastapi's handler function.

I have a script called `test_script.py` so my app can be found at `test_script:app`.
We use strings to resolve application to bypass circular imports.

Also, as you can see, we use `TaskiqDepends` for Request. That's because
taskiq dependency resolver must know that this type must be injected. FastAPI disallow
Depends for Request type. That's why we use `TaskiqDepends`.

```python
from fastapi import FastAPI, Request
from pydantic import BaseModel
from redis.asyncio import ConnectionPool, Redis
from fastapi import Depends as FastAPIDepends
from taskiq import TaskiqDepends
import taskiq_fastapi
from taskiq import ZeroMQBroker

broker = ZeroMQBroker()

app = FastAPI()


@app.on_event("startup")
async def app_startup():
    #####################
    # IMPORTANT NOTE    #
    #####################
    # If you won't check that this is not
    # a worker process, you'll
    # create an infinite recursion. Because in worker processes
    # fastapi startup will be called.
    if not broker.is_worker_process:
        print("Starting broker")
        await broker.startup()
    print("Creating redis pool")
    app.state.redis_pool = ConnectionPool.from_url("redis://localhost")


@app.on_event("shutdown")
async def app_shutdown():
    #####################
    # IMPORTANT NOTE    #
    #####################
    # If you won't check that this is not
    # a worker process, you'll
    # create an infinite recursion. Because in worker processes
    # fastapi startup will be called.
    if not broker.is_worker_process:
        print("Shutting down broker")
        await broker.shutdown()
    print("Stopping redis pool")
    await app.state.redis_pool.disconnect()


# Here we call our magic function.
taskiq_fastapi.init(broker, "test_script:app")


# We use TaskiqDepends here, because if we use FastAPIDepends fastapi
# initialization will fail.
def get_redis_pool(request: Request = TaskiqDepends()) -> ConnectionPool:
    return request.app.state.redis_pool


@broker.task
async def my_redis_task(
    key: str,
    val: str,
    # Here we depend using TaskiqDepends.
    # Please use TaskiqDepends for all tasks to be resolved correctly.
    # Or dependencies won't be injected.
    pool: ConnectionPool = TaskiqDepends(get_redis_pool),
):
    async with Redis(connection_pool=pool) as redis:
        await redis.set(key, val)
        print("Value set.")


class MyVal(BaseModel):
    key: str
    val: str


@app.post("/val")
async def setval_endpoint(val: MyVal) -> None:
    await my_redis_task.kiq(
        key=val.key,
        val=val.val,
    )
    print("Task sent")


@app.get("/val")
async def getval_endpoint(
    key: str,
    pool: ConnectionPool = FastAPIDepends(get_redis_pool),
) -> str:
    async with Redis(connection_pool=pool, decode_responses=True) as redis:
        return await redis.get(key)

```

## Manually update dependency context

When using `InMemoryBroker` it may be required to update the dependency context manually. This may also be useful when setting up tests.

```py
import taskiq_fastapi
from taskiq import InMemoryBroker

broker = InMemoryBroker()

app = FastAPI()

taskiq_fastapi.init(broker, "test_script:app")
taskiq_fastapi.populate_dependency_context(broker, app)
```
