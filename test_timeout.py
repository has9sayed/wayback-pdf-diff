import asyncio
from tornado.httpclient import AsyncHTTPClient
from tornado.simple_httpclient import HTTPTimeoutError

async def fetch():
    client = AsyncHTTPClient()
    try:
        await client.fetch("https://httpbin.org/delay/5", request_timeout=1.0)
    except HTTPTimeoutError as e:
        print("HTTPTimeoutError caught!")
    except Exception as e:
        print("Other exception:", repr(e))

asyncio.run(fetch())
