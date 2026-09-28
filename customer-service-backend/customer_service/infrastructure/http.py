
from httpx import AsyncClient

http_client: AsyncClient | None = None


def init_http_client():
    global http_client
    http_client = AsyncClient(timeout=10.0)


async def close_http_client():
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None
