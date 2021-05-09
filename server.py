#!/usr/bin/env python

# WS server example

import asyncio
import websockets

async def hello(websocket, path):
    async for message in websocket:
        name = message
        print(f"< {name}")

        greeting = f"Hello {name}!"

        await websocket.send(greeting)
        print(f"> {greeting}")

start_server = websockets.serve(hello, "localhost", 8765)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
