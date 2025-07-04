# Generated: 2025-07-04T09:50:40.107012
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

"""Shnifter Engine API.

Launch script and widgets builder for the Shnifter Workspace Custom Backend.
"""

import json
import logging
import os
import sys
from pathlib import Path

import uvicorn
from fastapi.responses import HTMLResponse, JSONResponse
from shnifter_core.api.rest_api import app
from shnifter_core.app.service.system_service import SystemService
from shnifter_core.env import Env

from .utils.api import check_port, get_user_settings, get_widgets_json, parse_args

logger = logging.getLogger("shnifter_engine_api")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter("\n%(message)s\n")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


FIRST_RUN = True

# Adds the Shnifter Environment variables to the script process.
Env()

HOME = os.environ.get("HOME") or os.environ.get("USERPROFILE")

if not HOME:
    raise ValueError("HOME or USERPROFILE environment variable not set.")

CURRENT_USER_SETTINGS = os.path.join(HOME, ".shnifter_engine", "user_settings.json")
USER_SETTINGS_COPY = os.path.join(HOME, ".shnifter_engine", "user_settings_backup.json")

# Widget filtering is optional and can be used to exclude widgets from the widgets.json file
# You can generate this filter on Shnifter Core: https://my.shnifter.co/app/engine/widgets
# Alternatively, you can supply a JSON-encoded list of API paths to ignore.
WIDGET_SETTINGS = os.path.join(HOME, ".shnifter_engine", "widget_settings.json")

kwargs = parse_args()

_app = kwargs.pop("app", None)

if _app:
    app = _app


# These are handled for backwards compatibility, and in ./utils/api::parse_args.
# It should be handled by this point in the code execution, but in case the key
# still exists for some reason, we will pop it so it doesn't get passed to uvicorn.run
# It would be reasonable to remove special handling by V1.3
WIDGETS_PATH = kwargs.pop("widgets-json", None) or kwargs.pop("widgets-path", None)
APPS_PATH = kwargs.pop("apps-json", None) or kwargs.pop("templates-path", None)

EDITABLE = kwargs.pop("editable", None) is True or WIDGETS_PATH is not None
DEFAULT_APPS_PATH = (
    Path(__file__).absolute().parent.joinpath("assets").joinpath("default_apps.json")
)
AGENTS_PATH = kwargs.pop("agents-json", None)
build = kwargs.pop("build", True)
build = False if kwargs.pop("no-build", None) else build
login = kwargs.pop("login", False)
dont_filter = kwargs.pop("no-filter", False)
widget_exclude_filter: list = kwargs.pop("exclude", [])

uvicorn_settings = (
    SystemService().system_settings.python_settings.model_dump().get("uvicorn", {})
)

for key, value in uvicorn_settings.items():
    if key not in kwargs and key != "app" and value is not None:
        kwargs[key] = value

if not dont_filter and os.path.exists(WIDGET_SETTINGS):
    with open(WIDGET_SETTINGS) as widget_settings_file:
        try:
            widget_exclude_filter_json = json.load(widget_settings_file).get(
                "exclude", []
            )
            if isinstance(widget_exclude_filter_json, list):
                widget_exclude_filter.extend(widget_exclude_filter_json)
        except json.JSONDecodeError as e:
            logger.info("Error loading widget filter settings -> %s", e)


openapi = app.openapi()

# We don't need the current settings,
# but we need to call the function to update, login, and/or identify the settings file.
current_settings = get_user_settings(login, CURRENT_USER_SETTINGS, USER_SETTINGS_COPY)
widgets_json = get_widgets_json(
    build, openapi, widget_exclude_filter, EDITABLE, WIDGETS_PATH
)

# A template file will be served from the ShnifterUserDataDirectory, if it exists.
# If it doesn't exist, an empty list will be returned, and an empty file will be created.
APPS_PATH = (
    APPS_PATH
    if APPS_PATH
    else (
        current_settings.get("preferences", {}).get(
            "data_directory", HOME + "/ShnifterUserData"
        )
        + "/workspace_apps.json"
    )
)


@app.get("/")
async def root():
    """Serve the landing page HTML content."""
    html_path = Path(__file__).parent / "assets" / "landing_page.html"
    with open(html_path) as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@app.get("/widgets.json")
async def get_widgets():
    """Widgets configuration file for the Shnifter Workspace."""
    # This allows us to serve an edited widgets.json file without reloading the server.
    global FIRST_RUN  # noqa PLW0603  # pylint: disable=global-statement
    if FIRST_RUN is True:
        FIRST_RUN = False
        return JSONResponse(content=widgets_json)
    if EDITABLE:
        return JSONResponse(
            content=get_widgets_json(
                False, openapi, widget_exclude_filter, EDITABLE, WIDGETS_PATH
            )
        )
    return JSONResponse(content=widgets_json)


# If a custom implementation, you might want to override.
@app.get("/apps.json")
async def get_apps_json():
    """Get the apps.json file."""
    new_templates: list = []
    default_templates: list = []
    widgets = await get_widgets()

    if not os.path.exists(APPS_PATH):
        apps_dir = os.path.dirname(APPS_PATH)
        if not os.path.exists(apps_dir):
            os.makedirs(apps_dir, exist_ok=True)
        # Write an empty file for the user to add exported apps from Workspace to.
        with open(APPS_PATH, "w", encoding="utf-8") as templates_file:
            templates_file.write(json.dumps([]))

    if os.path.exists(DEFAULT_APPS_PATH):
        with open(DEFAULT_APPS_PATH) as f:
            default_templates = json.load(f)

    if os.path.exists(APPS_PATH):
        with open(APPS_PATH) as templates_file:
            templates = json.load(templates_file)

        if isinstance(templates, dict):
            templates = [templates]

        templates.extend(default_templates)

        for template in templates:
            if _id := template.get("id"):
                if _id in widgets and template not in new_templates:
                    new_templates.append(template)
                    continue
            elif template.get("layout") or template.get("tabs"):
                if _tabs := template.get("tabs"):
                    for v in _tabs.values():
                        if v.get("layout", []) and all(
                            item.get("i") in widgets_json for item in v.get("layout")
                        ):
                            new_templates.append(template)
                            break
                elif (
                    template.get("layout")
                    and all(
                        item.get("i") in widgets_json for item in template["layout"]
                    )
                    and template not in new_templates
                ):
                    new_templates.append(template)

        if new_templates:
            return JSONResponse(content=new_templates)

    return JSONResponse(content=[])


if AGENTS_PATH:

    @app.get("/agents.json")
    async def get_agents():
        """Get the agents.json file."""
        if os.path.exists(AGENTS_PATH):
            with open(AGENTS_PATH) as f:
                agents = json.load(f)
            return JSONResponse(content=agents)
        return JSONResponse(content=[])


def launch_api(**_kwargs):  # noqa PRL0912
    """Main function."""
    host = _kwargs.pop("host", os.getenv("SHNIFTER_API_HOST", "127.0.0.1"))
    if not host:
        logger.info(
            "SHNIFTER_API_HOST is set incorrectly. It should be an IP address or hostname."
        )
        host = input("Enter the host IP address or hostname: ")
        if not host:
            host = "127.0.0.1"

    port = _kwargs.pop("port", os.getenv("SHNIFTER_API_PORT", "6900"))

    try:
        port = int(port)
    except ValueError:
        logger.info("SHNIFTER_API_PORT is set incorrectly. It should be an port number.")
        port = input("Enter the port number: ")
        try:
            port = int(port)
        except ValueError:
            logger.info("Invalid port number. Defaulting to 6900.")
            port = 6900
    if port < 1025:
        port = 6900
        logger.info("Invalid port number, must be above 1024. Defaulting to 6900.")

    free_port = check_port(host, port)

    if free_port != port:
        logger.info("Port %d is already in use. Using port %d.", port, free_port)
        port = free_port

    if "use_colors" not in _kwargs:
        _kwargs["use_colors"] = "win" not in sys.engine or os.name != "nt"

    try:
        package_name = __package__
        _msg = (
            "\nTo access this data from Shnifter Workspace, use the link displayed after the application startup completes."
            "\nChrome is the recommended browser. Other browsers may conflict or require additional configuration."
            f"\n{f'Documentation is available at {app.docs_url}.' if app.docs_url else ''}"
        )
        logger.info(_msg)
        uvicorn.run(f"{package_name}.main:app", host=host, port=port, **_kwargs)
    finally:
        # If user_settings_copy.json exists, then restore the original settings.
        if os.path.exists(USER_SETTINGS_COPY):
            logger.info("Restoring the original settings.")
            os.replace(USER_SETTINGS_COPY, CURRENT_USER_SETTINGS)


def main():
    """Launch the API."""
    launch_api(**kwargs)


if __name__ == "__main__":

    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
