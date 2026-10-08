"""Constants for Battery SoC."""

from typing import Final

DOMAIN: Final = "battery_soc"

# Sources and battery (config entry options)
CONF_CURRENT_ENTITY: Final = "current_entity"  # signed, + = charging
CONF_VOLTAGE_ENTITY: Final = "voltage_entity"
CONF_FULL_ENTITY: Final = "full_entity"  # optional binary_sensor, on = full (e.g. float charging)
CONF_GRID_ENTITY: Final = "grid_entity"  # optional binary_sensor, on = utility grid present
CONF_LOAD_ENTITY: Final = "load_power_entity"  # optional sensor, W drawn by the load (inverter output)
CONF_COUNTERS_ENTITY: Final = "counters_entity"  # optional: JSON totals kept on the inverter's ESP
CONF_BOOT_ENTITY: Final = "boot_entity"  # optional: JSON snapshot of those totals at the ESP's boot
CONF_NOMINAL_CAPACITY: Final = "nominal_capacity_ah"
CONF_NOMINAL_VOLTAGE: Final = "nominal_voltage"

# Detection and learning (config entry options)
CONF_EMPTY_VOLTAGE: Final = "empty_voltage"
CONF_EMPTY_DELAY: Final = "empty_delay_s"
CONF_SHUTDOWN_DELAY: Final = "shutdown_delay_s"
CONF_LOW_VOLTAGE_HINT: Final = "low_voltage_hint"
CONF_LOW_SOC_HINT: Final = "low_soc_hint"
CONF_FULL_VOLTAGE: Final = "full_voltage"
CONF_TAIL_CURRENT: Final = "tail_current_a"
CONF_FULL_DELAY: Final = "full_delay_s"
CONF_MAX_GAP: Final = "max_gap_s"
CONF_LEARN_CAPACITY: Final = "learn_capacity"
CONF_LEARN_EFFICIENCY: Final = "learn_efficiency"
CONF_LEARN_OFFSET: Final = "learn_current_offset"

# Config entry data (first setup only)
CONF_INITIAL_SOC: Final = "initial_soc"

DEFAULTS: Final = {
    CONF_NOMINAL_CAPACITY: 200.0,
    CONF_NOMINAL_VOLTAGE: 25.6,
    CONF_EMPTY_VOLTAGE: 24.0,
    CONF_EMPTY_DELAY: 10,
    CONF_SHUTDOWN_DELAY: 180,
    CONF_LOW_VOLTAGE_HINT: 25.0,
    CONF_LOW_SOC_HINT: 20,
    CONF_FULL_VOLTAGE: 28.2,
    CONF_TAIL_CURRENT: 10.0,
    CONF_FULL_DELAY: 60,
    CONF_MAX_GAP: 300,
    CONF_LEARN_CAPACITY: True,
    CONF_LEARN_EFFICIENCY: True,
    CONF_LEARN_OFFSET: True,
}

DEFAULT_EFFICIENCY: Final = 0.95
EFFICIENCY_RANGE: Final = (0.80, 1.00)
CAPACITY_RANGE: Final = (0.50, 1.20)  # of nominal
LEARN_ALPHA: Final = 0.3  # EMA weight of a new cycle
LEARN_MIN_CYCLE: Final = 0.10  # of capacity; shorter cycles teach nothing
OFFSET_RANGE: Final = (-5.0, 5.0)  # A
OFFSET_MIN_SECONDS: Final = 1800  # of float per offset sample
OFFSET_MAX_SECONDS: Final = 3600  # a long float gives one sample per hour
DEFAULT_LOAD_RATIO: Final = 1.0  # battery W per load W
LOAD_RATIO_RANGE: Final = (0.8, 1.5)
LOAD_LEARN_MIN_AH: Final = 10.0  # discharged per outage to learn the load ratio
LOAD_ON_POWER: Final = 10.0  # W; a load sensor above this means the inverter still runs
COUNTER_FIELDS: Final = ("ai", "ao", "si", "so", "fa", "fs", "wi", "wo")
IDLE_CURRENT: Final = 0.5  # A; below this the battery counts as idle
TICK_SECONDS: Final = 10

# Bus events fired for automations
EVENT_FULL: Final = f"{DOMAIN}_full"
EVENT_EMPTY: Final = f"{DOMAIN}_empty"

SERVICE_SET_SOC: Final = "set_soc"
ATTR_SOC: Final = "soc"

STORAGE_VERSION: Final = 1
