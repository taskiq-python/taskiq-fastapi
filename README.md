# Taskiq + FastAPI

This repository provides code to integrate FastAPI with Taskiq easily.

Taskiq and FastAPI both use dependency injection, but they function differently. This library bridges the gap, allowing you to depend on `fastapi.Request` or `starlette.requests.HTTPConnection` inside your Taskiq tasks.

With this library, you can easily re-use your FastAPI dependencies (like database pools or config loaders) inside your Taskiq background functions.

## How does it work?

### 1. Process Separation
Taskiq tasks usually run in a separate **Worker process**, not inside your FastAPI web server process. (_It does not run within event loop_)

### 2. Context Bridging
When the Worker starts, this library initializes your FastAPI application in the background.

### 3. Dependency Injection
It creates a **dummy Request object** within the Worker. This allows functions that need FastAPI request context (like accessing `app.state`) to work identically in both the Web App and the Background Worker.

> **Note:** The injected Request object in a task is **NOT** the original HTTP request from the user. It is a simulated request context solely for accessing application state.

---

## Usage Example

### File: `test_script.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends as FastAPIDepends
from pydantic import BaseModel
from redis.asyncio import ConnectionPool, Redis
from taskiq import TaskiqDepends, ZeroMQBroker
import taskiq_fastapi

broker = ZeroMQBroker()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Creating redis pool")
    app.state.redis_pool = ConnectionPool.from_url("redis://localhost")
    #####################
    # IMPORTANT NOTE    #
    #####################
    # If you won't check that this is not
    # a worker process, you'll
    # create an infinite recursion. Because in worker processes
    # fastapi startup will be called.
    if not broker.is_worker_process:
        print("Starting broker client")
        await broker.startup()

    yield # waits for shutdown

    #####################
    # IMPORTANT NOTE    #
    #####################
    # Same as above
    if not broker.is_worker_process:
        print("Shutting down broker client")
        await broker.shutdown()

    print("Stopping redis pool")
    await app.state.redis_pool.disconnect()

app = FastAPI(lifespan=lifespan)

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
    await my_redis_task.kiq(key=val.key, val=val.val)
    print("Task sent")

@app.get("/val")
async def getval_endpoint(
    key: str,
    pool: ConnectionPool = FastAPIDepends(get_redis_pool),
) -> str:
    async with Redis(connection_pool=pool, decode_responses=True) as redis:
        return await redis.get(key)
```

---

## Key Takeaways

### `if not broker.is_worker_process`

- **True for FastAPI server (uvicorn)** → lifespan starts broker client so tasks can be sent.
- **False for Taskiq worker** → worker manages its own broker connection; lifespan still initializes dependencies.

Prevents double-starting the broker.

### `TaskiqDepends` vs `FastAPIDepends`

| Purpose | Use |
|--------|------|
| Inside Taskiq tasks | `TaskiqDepends` |
| Inside HTTP routes | `FastAPIDepends` |

---

## Manual Dependency Context Update (InMemoryBroker)

When using `InMemoryBroker` (often used for unit testing) it may be required to update the dependency context manually, as there is no separate worker process to trigger the initialization.

```python
import taskiq_fastapi
from taskiq import InMemoryBroker
from fastapi import FastAPI

broker = InMemoryBroker()
app = FastAPI()

taskiq_fastapi.init(broker, "test_script:app")
taskiq_fastapi.populate_dependency_context(broker, app)
```

---

## Deployment with Docker (Single Artifact Pattern)

The best way to deploy this system is to use the Single Artifact pattern. You build one Docker image that contains your entire codebase, and you run it with different commands to start the API or the Worker.

### 1. Dockerfile

This Dockerfile copies your code and installs dependencies. It does not specify a `CMD` because we will set that in `docker-compose.yml`.

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
```

### 2. docker-compose.yml

Notice how api and worker use the same build: . context but run different commands.

```yaml
version: "3.8"

services:
  api:
    build: .
    container_name: fastapi_app
    command: uvicorn test_script:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - NATS_URL=nats://nats:4222
    depends_on:
      - nats

  worker:
    build: .
    container_name: taskiq_worker
    command: taskiq worker test_script:broker
    environment:
      - NATS_URL=nats://nats:4222
    depends_on:
      - nats

  nats:
    image: nats:latest
    ports:
      - "4222:4222"
```

### Run the stack

```bash
docker-compose up --build
```

You may also run it individually using `docker run` or integrate into the kubernetes environment.

---
