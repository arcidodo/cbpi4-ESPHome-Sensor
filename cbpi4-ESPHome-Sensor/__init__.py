from cbpi.api import *
import asyncio, logging
from aioesphomeapi import APIClient, APIConnectionError

logger = logging.getLogger(__name__)

@parameters([
    Property.Select("Type", options=["CO2", "Temperature", "Relative Humidity"],
                     description="Select type of data to register for this sensor."),
    Property.Number(label="Request Timeout", configurable=True,
                     description="Connectie/reconnect timeout in seconden (default 5)", default_value=5),
    Property.Text(label="Host", configurable=True,
                   description="IP-adres van de ESPHome node (bv. 192.168.1.50)"),
    Property.Number(label="Port", configurable=True, default_value=6053,
                     description="Native API poort van ESPHome (standaard 6053)"),
    Property.Text(label="Encryption Key", configurable=True,
                   description="API encryption key (base64) uit je ESPHome yaml onder 'api: encryption: key:'. Leeg laten indien niet gebruikt."),
    Property.Text(label="Entity Name", configurable=True,
                   description="Naam (of id) van de sensor zoals gedefinieerd in de ESPHome yaml."),
])


class ESPHomeSensor(CBPiSensor):

    async def on_start(self):
        self.value = 0  # initial value visible to CBPi4 UI
        self.host = self.props.get("Host")
        self.port = int(self.props.get("Port", 6053))
        key = self.props.get("Encryption Key") or None
        self.client = APIClient(self.host, self.port, password="", noise_psk=key)
        self.entity_name = self.props.get("Entity Name")
        self.timeout = float(self.props.get("Request Timeout", 5))
        self.entity_key = None
        self.connected = False

    async def run(self):
        while self.running:
            if not self.connected:
                try:
                    await self.client.connect(login=True)
                    entities, _ = await self.client.list_entities_services()

                    self.entity_key = None
                    for e in entities:
                        if e.name == self.entity_name or getattr(e, "object_id", None) == self.entity_name:
                            self.entity_key = e.key
                            break

                    if self.entity_key is None:
                        logger.error(f"ESPHome entity '{self.entity_name}' niet gevonden op {self.host}")
                        await self.client.disconnect()
                        await asyncio.sleep(self.timeout)
                        continue

                    self.client.subscribe_states(self._on_state)
                    self.connected = True
                    logger.info(f"Verbonden met ESPHome node {self.host}, entity key {self.entity_key}")

                except (APIConnectionError, OSError, TimeoutError) as e:
                    logger.error(f"ESPHome verbindingsfout ({self.host}): {e}")
                    self.connected = False
                    await asyncio.sleep(self.timeout)
                    continue

            await asyncio.sleep(1)

    def _on_state(self, state):
        if getattr(state, "key", None) == self.entity_key and hasattr(state, "state"):
            try:
                self.value = round(float(state.state), 2)
                self.log_data(self.value)
                self.push_update(self.value)
                logger.info(f"Sensor updated: {self.value}")
            except (TypeError, ValueError):
                pass

    async def on_stop(self):
        try:
            await self.client.disconnect()
        except Exception:
            pass
        self.connected = False

    def get_state(self):
        return dict(value=self.value)


def setup(cbpi):
    cbpi.plugin.register("ESPHome Sensor", ESPHomeSensor)
    pass