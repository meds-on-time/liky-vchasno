"""Menu commands match the bot handlers."""

from app.bot_commands import COMMANDS


def test_menu_has_all_commands():
    names = [c.command for c in COMMANDS]
    assert names == ["start", "add", "meds", "times", "invite", "consent_on", "consent_off", "cancel"]


def test_every_command_has_description():
    assert all(c.description for c in COMMANDS)