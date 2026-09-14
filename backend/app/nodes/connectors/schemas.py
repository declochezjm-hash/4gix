"""Schémas de paramètres style n8n (Send and Wait for Response)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _response_type_field() -> Dict[str, Any]:
    return {
        "type": "string",
        "title": "Response Type",
        "enum": ["approval", "freeText", "customForm"],
        "enumNames": ["Approval", "Free Text", "Custom Form"],
        "default": "approval",
        "description": "Type de réponse attendue avant de reprendre le workflow.",
    }


def _show_when(**conditions: Any) -> Dict[str, Any]:
    return {"x-showWhen": conditions}


def _approval_fields() -> Dict[str, Any]:
    return {
        "approval_type": {
            "type": "string",
            "title": "Approval Type",
            "enum": ["single", "double"],
            "enumNames": ["Approve only", "Approve and Disapprove"],
            "default": "single",
            **_show_when(response_type="approval"),
        },
        "approve_label": {
            "type": "string",
            "title": "Approve Button Label",
            "default": "Approve",
            **_show_when(response_type="approval"),
        },
        "disapprove_label": {
            "type": "string",
            "title": "Disapprove Button Label",
            "default": "Disapprove",
            **_show_when(response_type="approval", approval_type="double"),
        },
        "capture_responder": {
            "type": "boolean",
            "title": "Capture Who Responded",
            "default": True,
            "description": "Enregistre l'identité de la personne qui a répondu.",
            **_show_when(response_type="approval"),
        },
    }


def _wait_limit_fields() -> Dict[str, Any]:
    return {
        "limit_wait_time": {
            "type": "boolean",
            "title": "Limit Wait Time",
            "default": True,
        },
        "wait_amount": {
            "type": "integer",
            "title": "Wait Amount",
            "default": 30,
            "minimum": 1,
            **_show_when(limit_wait_time=True),
        },
        "wait_unit": {
            "type": "string",
            "title": "Wait Unit",
            "enum": ["minutes", "hours", "days"],
            "enumNames": ["Minutes", "Hours", "Days"],
            "default": "minutes",
            **_show_when(limit_wait_time=True),
        },
    }


def _base_send_wait_properties(
    *,
    recipient_title: str,
    recipient_description: str = "",
    recipient_default: str = "",
    show_select: bool = False,
    show_subject: bool = False,
    extra: Optional[Dict[str, Any]] = None,
    credential_type: str = "integration",
) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "credential": {
            "type": "string",
            "title": "Credential to connect with",
            "description": "Identifiant du compte / jeton configuré (équivalent n8n).",
            "default": "",
            "format": "credential",
            "credentialType": credential_type,
        },
        "resource": {
            "type": "string",
            "title": "Resource",
            "enum": ["message"],
            "enumNames": ["Message"],
            "default": "message",
        },
        "operation": {
            "type": "string",
            "title": "Operation",
            "enum": ["sendAndWait"],
            "enumNames": ["Send and Wait for Response"],
            "default": "sendAndWait",
        },
    }
    if show_select:
        props["select"] = {
            "type": "string",
            "title": "Send Message To",
            "enum": ["channel", "user"],
            "enumNames": ["Channel", "User"],
            "default": "channel",
        }
    props["recipient"] = {
        "type": "string",
        "title": recipient_title,
        "description": recipient_description,
        "default": recipient_default,
    }
    if show_subject:
        props["subject"] = {
            "type": "string",
            "title": "Subject",
            "default": "",
        }
    props["message"] = {
        "type": "string",
        "title": "Message",
        "format": "textarea",
        "default": "",
        "description": "Contenu envoyé à l'utilisateur (Markdown supporté selon le canal).",
    }
    props["response_type"] = _response_type_field()
    props.update(_approval_fields())
    props["message_button_label"] = {
        "type": "string",
        "title": "Response Form Button Label",
        "default": "Respond",
        "description": "Libellé du bouton pour Free Text / Custom Form.",
        **_show_when(response_type=["freeText", "customForm"]),
    }
    props.update(_wait_limit_fields())
    props["append_attribution"] = {
        "type": "boolean",
        "title": "Append n8n Attribution",
        "default": True,
    }
    if extra:
        props.update(extra)
    return props


def send_and_wait_schema(
    title: str,
    template: str,
    description: str = "",
    credential_type: Optional[str] = None,
) -> Dict[str, Any]:
    templates = {
        "slack": lambda: _base_send_wait_properties(
            show_select=True,
            credential_type="slack",
            recipient_title="Channel / User ID",
            recipient_description="ID Slack du canal (C…) ou de l'utilisateur (U…).",
        ),
        "discord": lambda: _base_send_wait_properties(
            show_select=True,
            credential_type="discord",
            recipient_title="Channel ID",
            recipient_description="Identifiant du salon Discord.",
        ),
        "teams": lambda: _base_send_wait_properties(
            show_select=True,
            credential_type="microsoftTeams",
            recipient_title="Team / Channel ID",
            recipient_description="Identifiant d'équipe ou de canal Teams.",
        ),
        "google_chat": lambda: _base_send_wait_properties(
            credential_type="googleChat",
            recipient_title="Space name",
            recipient_description="Nom ou ID de l'espace Google Chat.",
        ),
        "email": lambda: _base_send_wait_properties(
            show_subject=True,
            credential_type="gmail",
            recipient_title="To",
            recipient_description="Adresse e-mail du destinataire.",
        ),
        "telegram": lambda: _base_send_wait_properties(
            credential_type="telegram",
            recipient_title="Chat ID",
            recipient_description="ID de chat Telegram.",
        ),
        "whatsapp": lambda: _base_send_wait_properties(
            credential_type="whatsApp",
            recipient_title="Phone Number ID / To",
            recipient_description="Numéro WhatsApp Business ou ID destinataire.",
        ),
        "outlook": lambda: _base_send_wait_properties(
            show_subject=True,
            credential_type="microsoftOutlook",
            recipient_title="To",
            recipient_description="Adresse Microsoft Outlook.",
        ),
    }
    builder = templates.get(template, templates["slack"])
    props = builder()
    if credential_type:
        props["credential"]["credentialType"] = credential_type
    return {
        "title": title,
        "description": description or "Send and wait for response (n8n-compatible parameters).",
        "type": "object",
        "properties": props,
        "required": ["message"],
    }


def human_approval_schema() -> Dict[str, Any]:
    return {
        "title": "Human in the loop",
        "description": "Wait for approval or human input before continuing.",
        "type": "object",
        "properties": {
            "credential": {
                "type": "string",
                "title": "Credential to connect with",
                "default": "",
                "format": "credential",
                "credentialType": "humanApproval",
            },
            "message": {
                "type": "string",
                "title": "Message",
                "format": "textarea",
                "default": "Please review the data and approve to continue.",
            },
            "response_type": _response_type_field(),
            **_approval_fields(),
            "message_button_label": {
                "type": "string",
                "title": "Response Form Button Label",
                "default": "Respond",
                **_show_when(response_type=["freeText", "customForm"]),
            },
            **_wait_limit_fields(),
        },
        "required": ["message"],
    }


def integration_connector_schema(title: str, description: str = "") -> Dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "type": "object",
        "properties": {
            "credential": {
                "type": "string",
                "title": "Credential to connect with",
                "default": "",
            },
            "resource": {
                "type": "string",
                "title": "Resource",
                "default": "default",
            },
            "operation": {
                "type": "string",
                "title": "Operation",
                "default": "execute",
            },
            "parameters": {
                "type": "string",
                "title": "Parameters (JSON)",
                "format": "textarea",
                "default": "{}",
            },
        },
    }
