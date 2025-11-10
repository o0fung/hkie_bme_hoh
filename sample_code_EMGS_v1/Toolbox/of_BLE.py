import asyncio
from dataclasses import dataclass
from bleak import BleakScanner, BleakClient


@dataclass
class BLE:
    name: str = None
    uuid_dev: str = None
    uuid_read: str = None
    uuid_write: str = None
    uuid_notify: str = None
    uuid_desc: str = None
    client: BleakClient = None
    
    def run_asyncio(func):
        # Decorator to asyncio run any function
        def inner(self, *args, **kwargs):
            return asyncio.run(func(self, *args, **kwargs))
        
        return inner
    
    @run_asyncio
    async def scan(self):
        # Scan nearby BLE device
        
        print("\n>> Scan nearby BLE devices...\n")
        # Scan and list devices
        devices = await BleakScanner.discover()
        for device in devices:
            print(device)
            
    @run_asyncio    
    async def show_services(self, uuid=None):
        # Show target BLE device services and its characteristics
        
        if uuid is None:
            # Show services of selected UUID if available, otherwire terminate
            if self.uuid_dev is None:
                return
            uuid = self.uuid_dev
        
        async with BleakClient(uuid) as client:
            # Connect to the device
            if client.is_connected:
                print(f"\n>> Connected to Device UUID: {uuid}\n")
                
                # List characteristics of the device
                services = client.services
                for service in services:
                    print(f"\n>> Service UUID: {service.uuid}")
                    print(f"     Description: {service.description}")
                    for characteristic in service.characteristics:
                        characteristic.description
                        print(f"\n>>   Characteristic UUID: {characteristic.uuid}")
                        print(f"       Description: {characteristic.description}")
            else:
                print("\n>> Failed to connect to device.")
    
    async def connect(self):
        # Connect to a BLE device to read and write characteristics indefinitely
        
        if self.uuid_dev is None:
            # No BLE device is provided
            return
        
        try:
            self.client = BleakClient(self.uuid_dev)
            
            # Detect attempt to reconnect, then disconnect before connect again
            if self.client.is_connected:
                await self.client.disconnect()
            await self.client.connect()
            
        except Exception as e:
            print(f">> Device {self.name}: Failed to connect to the device UUID: {self.uuid_dev}")
            print(f">> {e}")
                
        # Connect to the device
        if not self.client.is_connected:
            return
        
        print(f">> Device {self.name}: Connected to UUID: {self.uuid_dev}")
    
    async def handler_read(self):
        # Read from characteristic if available
        if self.uuid_read is None:
            return
        
        while True:
            try:
                # Start a loop to read values from characteristic if available
                data = await self.client.read_gatt_char(self.uuid_read)
                print(f"\n>> Device {self.name}: Read characteristic value from {self.client}: {data.decode('utf-8')}")
                
            except Exception as e:
                print(f"\n>> Device {self.name}: Failed to read characteristic: {e}")
                
            await asyncio.sleep(1)
    
    async def handler_write(self, data):
        # Write to characteristic if available
        if self.uuid_write is None:
            return
        
        await self.client.write_gatt_char(self.uuid_write, data)
                
    async def handler_start_notify(self):
        # Start notification if characteristic available
        if self.uuid_notify is not None:
            # Start a task to receive notification from the characteristic indefinitely if available
            await self.client.start_notify(self.uuid_notify, self.handler_notify)
            print(f">> Device {self.name}: Started subscribed to notifications. Waiting for notifications...")
    
    async def handler_stop_notify(self):
        # Stop notification if characteristic available
        if self.uuid_notify is not None:
            # Start a task to receive notification from the characteristic indefinitely if available
            await self.client.stop_notify(self.uuid_notify)
            print(f">> Device {self.name}: Stopped subscribed to notifications...")
            
    def handler_notify(self, client, data):
        # Callback function to run when received notification
        print(f">> Device {self.name}: Received notification value from {self.client}: {data.decode('utf-8')}")
    
    async def disconnect(self):
        # Disconnect to the device
        await self.client.disconnect()
        print(f">> Device {self.name}: Disconnected to UUID: {self.uuid_dev}")
            
    

if __name__ == '__main__':
    print(">> Begin...")

    ble = BLE()
    ble.scan()
    # ble.show_services(uuid='')
