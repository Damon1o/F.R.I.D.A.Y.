from flask import Blueprint, render_template, request, jsonify

from core.context_loader import register_skill
from pages.calendar.actions import (
    add_event,
    delete_event,
    list_events,
    update_event,
)
from pages.chat.routes import TOOL_DISPATCH

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/calendar")
def calendar_page():
    return render_template("calendar.html")


@calendar_bp.route("/calendar/api/events")
def calendar_events_api():
    start = request.args.get("start")
    end = request.args.get("end")
    return jsonify(list_events(start_range=start, end_range=end))


CALENDAR_TOOLS = [
    {
        "name": "add_event",
        "description": "Add a new calendar event. Ask the user first if recurrence "
        "or duration is unclear rather than guessing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_datetime": {"type": "string", "description": "ISO-8601"},
                "end_datetime": {"type": "string", "description": "ISO-8601"},
                "recurrence_rule": {
                    "type": "string",
                    "enum": ["none", "daily", "weekly", "monthly"],
                },
                "notes": {"type": "string"},
            },
            "required": ["title", "start_datetime", "end_datetime"],
        },
    },
    {
        "name": "update_event",
        "description": "Update fields on an existing event by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "title": {"type": "string"},
                "start_datetime": {"type": "string"},
                "end_datetime": {"type": "string"},
                "recurrence_rule": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_event",
        "description": "Delete an event by id. Confirm with the user before "
        "deleting if the request is ambiguous about which event is meant.",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "integer"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "list_events",
        "description": "List events between two ISO-8601 datetimes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_range": {"type": "string"},
                "end_range": {"type": "string"},
            },
            "required": ["start_range", "end_range"],
        },
    },
]

register_skill(
    "calendar",
    system_prompt=(
        "The user is on the Calendar page. You can add, update, delete, and list "
        "events with the provided tools. If recurrence or any other required "
        "detail is missing or ambiguous, ask the user directly instead of "
        "guessing."
    ),
    tools=CALENDAR_TOOLS,
)

TOOL_DISPATCH.update(
    {
        "add_event": add_event,
        "update_event": update_event,
        "delete_event": delete_event,
        "list_events": list_events,
    }
)