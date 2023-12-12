import asyncio
from bleak import BleakClient

address = "F8:30:02:33:53:09"
MODEL_NBR_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
DATA_IN_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
DATA_OUT_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# Commands specific to the OmniDesk bluetooth controller.
# These commands were reverse engineered using packet captures of the bluetooth traffic.
DESK_UP_GATT_CMD = b"\xF1\xF1\x06\x00\x06\x7E"  # command will move desk to height preset 2
DESK_DOWN_GATT_CMD = b"\xF1\xF1\x05\x00\x05\x7E"  # command will move desk to height preset 1
DESK_STOP_GATT_CMD = b"\xF1\xF1\x2b\x00\x2b\x7E"  # command will stop the desk from moving


def get_height_in_cm(data: bytes) -> float:
    """Takes binary data from the height update notification and converts it to a height in cm.

    :param data: data from the height update notification
    :returns: the height in centimeters
    """

    height = int.from_bytes(data[-5:-3], "big") / 10.0

    return height


def callback(sender, data):
    height = get_height_in_cm(data)
    print(height)


async def main(address):
    async with BleakClient(address) as client:
        for service in client.services:
            for char in service.characteristics:
                print(char)
                print(char.handle)
                print(char.properties)

        model_number = await client.read_gatt_char(MODEL_NBR_UUID)
        print("Model Number: {0}".format("".join(map(chr, model_number))))

        await client.write_gatt_char(DATA_IN_UUID, DESK_DOWN_GATT_CMD)
        await client.start_notify(DATA_OUT_UUID, callback)
        await asyncio.sleep(10)


asyncio.run(main(address))


# import asyncio
# from bleak import BleakScanner

# async def main():
#     devices = await BleakScanner.discover()
#     for d in devices:
#         print(d)

# asyncio.run(main())
