"""Services of the DSC Neo integration that are not entity services."""

from __future__ import annotations

from typing import Any

from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.components.alarm_control_panel import (
    DOMAIN as ALARM_CONTROL_PANEL_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ServiceValidationError,
    Unauthorized,
    UnknownUser,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .pyneohub.client import FAP_TYPES

SERVICE_ACTIVATE_FAP = "activate_fap"
ATTR_FAP_TYPE = "type"
ATTR_CONFIRM = "confirm"


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services of the integration."""
    # No schema: _async_activate_fap checks every argument itself, so that
    # each invalid call fails with a ServiceValidationError (and sends
    # nothing) instead of a schema error.
    hass.services.async_register(DOMAIN, SERVICE_ACTIVATE_FAP, _async_activate_fap)


def _invalid(translation_key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=translation_key,
        translation_placeholders=placeholders or None,
    )


def _single_entity_id(value: Any) -> str:
    """Return the one entity ID of a call, or raise ServiceValidationError.

    It accepts a string or a list with exactly one string (the form of a
    "target"), never "all", "none" or a comma-separated list.
    """
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if (
        not isinstance(value, str)
        or value.strip().lower() in ("all", "none")
        or "," in value
        or not value.startswith(f"{ALARM_CONTROL_PANEL_DOMAIN}.")
    ):
        raise _invalid("fap_one_entity")
    return value


async def _async_check_permission(call: ServiceCall, entity_id: str) -> None:
    """Refuse a caller that may not control the entity, as entity services do.

    A plain domain service does not get Home Assistant's per-entity
    permission check, so without this a read-only user could raise a real
    alarm. Like an entity service: a call without a user (an automation, or
    a script started without one) is not limited, an unknown user raises
    UnknownUser and a user without control permission for the entity raises
    Unauthorized.
    """
    user_id = call.context.user_id
    if not user_id:
        return
    user = await call.hass.auth.async_get_user(user_id)
    if user is None:
        raise UnknownUser(
            context=call.context, user_id=user_id, permission=POLICY_CONTROL
        )
    if not user.permissions.check_entity(entity_id, POLICY_CONTROL):
        raise Unauthorized(
            context=call.context,
            user_id=user_id,
            entity_id=entity_id,
            permission=POLICY_CONTROL,
        )


def _alarm_panel(hass: HomeAssistant, entity_id: str) -> Entity:
    """Return the integration's loaded, enabled alarm panel entity."""
    for platform in entity_platform.async_get_platforms(hass, DOMAIN):
        if platform.domain != ALARM_CONTROL_PANEL_DOMAIN:
            continue
        entity = platform.entities.get(entity_id)
        if entity is not None and hasattr(entity, "async_activate_fap"):
            return entity
    raise _invalid("fap_unknown_entity", entity_id=entity_id)


async def _async_activate_fap(call: ServiceCall) -> None:
    """Send a FAP alarm for exactly one alarm panel entity (experimental).

    Every argument is checked before anything is sent: exactly one alarm
    panel entity of this integration (entity_id, as data or as a target;
    devices, areas, floors and labels are not accepted), "type" exactly
    fire, auxiliary or panic, and "confirm" exactly true. The caller must
    be allowed to control that entity.
    """
    data = dict(call.data)
    extra = sorted(set(data) - {ATTR_ENTITY_ID, ATTR_FAP_TYPE, ATTR_CONFIRM})
    if extra:
        raise _invalid("fap_invalid_keys", keys=", ".join(map(str, extra)))
    entity_id = _single_entity_id(data.get(ATTR_ENTITY_ID))
    fap_type = data.get(ATTR_FAP_TYPE)
    if not isinstance(fap_type, str) or fap_type not in FAP_TYPES:
        raise _invalid("fap_invalid_type")
    if data.get(ATTR_CONFIRM) is not True:
        raise _invalid("fap_not_confirmed")
    await _async_check_permission(call, entity_id)
    entity = _alarm_panel(call.hass, entity_id)
    await entity.async_activate_fap(fap_type)
