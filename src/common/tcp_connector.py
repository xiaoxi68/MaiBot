import ssl
import certifi
import aiohttp
import asyncio

ssl_context = ssl.create_default_context(cafile=certifi.where())
connector = None

async def get_tcp_connector():
    global connector
    if connector is None:
        connector = aiohttp.TCPConnector(ssl=ssl_context)
    return connector
