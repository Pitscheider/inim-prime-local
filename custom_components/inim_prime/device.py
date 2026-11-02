"""Shared helpers for zone label language and per-room device grouping."""

from __future__ import annotations

import unicodedata

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_GROUP_BY_ROOM,
    CONF_LABEL_LANGUAGE,
    DEFAULT_GROUP_BY_ROOM,
    DOMAIN,
    LABEL_LANGUAGE_AUTO,
)
from .coordinator import InimDataUpdateCoordinator


def panel_device_info(coordinator: InimDataUpdateCoordinator) -> DeviceInfo:
    """Build the DeviceInfo for the panel hub device.

    Firmware and model come from the panel's version string read natively at
    setup (e.g. ``"5.00 PX020"``).
    """
    entry = coordinator.config_entry
    version = coordinator.data.version

    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="INIM",
        model=version.model_name,
        sw_version=version.firmware,
        name=entry.title,
    )


def label_language(coordinator: InimDataUpdateCoordinator) -> str:
    """Resolve the language used to guess zone device classes/rooms from labels.

    Uses the per-entry override option when set, otherwise the Home Assistant
    system language (``hass.config.language``).
    """
    configured = coordinator.config_entry.options.get(
        CONF_LABEL_LANGUAGE, LABEL_LANGUAGE_AUTO
    )
    if configured and configured != LABEL_LANGUAGE_AUTO:
        return str(configured)
    return coordinator.hass.config.language


def group_zones_by_room(coordinator: InimDataUpdateCoordinator) -> bool:
    """Whether zones should be grouped under per-room devices."""
    return bool(
        coordinator.config_entry.options.get(
            CONF_GROUP_BY_ROOM, DEFAULT_GROUP_BY_ROOM
        )
    )


def _room_slug(room: str) -> str:
    """Stable identifier fragment for a room name (accent-folded, underscored)."""
    folded = "".join(
        c
        for c in unicodedata.normalize("NFKD", room.lower())
        if not unicodedata.combining(c)
    )
    return "_".join(folded.split())


def _room_identifier_prefix(entry: ConfigEntry) -> str:
    """The start of every room device identifier of an entry."""
    return f"{entry.entry_id}_room_"


def room_device_info(
    coordinator: InimDataUpdateCoordinator, room: str
) -> DeviceInfo:
    """Build the DeviceInfo for a per-room sub-device linked to the panel."""
    entry = coordinator.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, f"{_room_identifier_prefix(entry)}{_room_slug(room)}")},
        name=room,
        manufacturer="INIM",
        via_device=(DOMAIN, entry.entry_id),
    )


@callback
def async_remove_empty_room_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the room devices of an entry that no entity uses any more.

    That happens when room grouping is turned off, or when a zone renamed on
    the panel no longer names its room. Run it after the platforms have added
    their entities. Disabled entities still count, so their room stays.
    """
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    prefix = _room_identifier_prefix(entry)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        is_room = any(
            domain == DOMAIN and identifier.startswith(prefix)
            for domain, identifier in device.identifiers
        )
        if is_room and not er.async_entries_for_device(
            entities, device.id, include_disabled_entities=True
        ):
            devices.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
