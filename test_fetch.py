import asyncio
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

async def fetch():
    client = AsyncHTTPClient()
    req = HTTPRequest(
        url="https://web.archive.org/web/20130301000000id_/https://www.irs.gov/pub/irs-pdf/fw4.pdf",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    )
    print("Fetching...")
    response = await client.fetch(req)
    print("Code:", response.code)

asyncio.run(fetch())
