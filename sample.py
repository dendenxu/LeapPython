import asyncio
import websockets
import json


async def demo():
    uri = "ws://localhost:6437/v7.json"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"focused": True}))
        await ws.send(json.dumps({"optimizeHMD": False}))
        print(f"Focused on the leap motion controller...")
        while True:
            # always waiting for messages
            msg = json.loads(await ws.recv())
            if "timestamp" in msg:
                hands = msg["hands"]
                if len(hands) > 0:
                    print(f"Getting {len(hands)} hands")
                else:
                    print(f"No hands hans been found")
            else:
                print(f"Getting message: {msg}")


asyncio.get_event_loop().run_until_complete(demo())
