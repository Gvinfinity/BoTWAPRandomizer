"""Connect Archipelago's standard client window to the bundled BotW bridge."""
import asyncio
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree

from CommonClient import CommonContext
from MultiServer import CommandProcessor
from NetUtils import HintStatus
from Utils import env_cleared_lib_path, open_directory, open_filename, user_path
from kvui import GameManager, status_colors, status_names
from .Launcher import bundled_patcher

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.metrics import dp
from kivy.utils import escape_markup
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

logger = logging.getLogger("Client")
BOTW_TITLE_IDS = ("00050000101c9500", "00050000101c9400", "00050000101c9300")


def installed_title_id(executable, windows):
    data_dir = executable.parent if windows else Path(
        os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    ) / "Cemu"
    try:
        titles = ElementTree.parse(data_dir / "title_list_cache.xml").getroot()
    except (OSError, ElementTree.ParseError):
        return BOTW_TITLE_IDS[0]
    return next((title_id for title in titles.iter("title")
                 if (title_id := title.get("titleId", "").lower()) in BOTW_TITLE_IDS), BOTW_TITLE_IDS[0])


def launch_cemu(windows):
    settings_path = Path(user_path("BotWAP", "cemu.json"))
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    executable = settings.get("executable") or shutil.which("Cemu.exe" if windows else "Cemu")
    if not executable and not windows:
        executable = shutil.which("cemu")
    if not executable or not Path(executable).is_file():
        executable = open_filename("Select the Cemu executable", [
            ("Cemu", (".exe",) if windows else (".AppImage",)),
            ("All files", ("*",)),
        ])
    if not executable:
        return None
    # Keep the selected executable's name, including symlinks to launcher binaries.
    executable = Path(os.path.abspath(executable))
    saved = {"executable": str(executable)}
    if title_id := settings.get("title_id"):
        saved["title_id"] = title_id
    else:
        title_id = installed_title_id(executable, windows)
    if saved != settings:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(saved), encoding="utf-8")
    return subprocess.Popen(
        [executable, "--title-id", title_id], cwd=executable.parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env_cleared_lib_path(),
    )


class BotWCommands(CommandProcessor):
    def __init__(self, ctx):
        self.ctx = ctx

    def output(self, text):
        logger.info(text)

    def default(self, raw):
        text = self.ctx.on_user_say(raw)
        if text:
            asyncio.create_task(self.ctx.say(text))

    def _cmd_connect(self, address=""):
        """Connect to an Archipelago room."""
        if address:
            self.ctx.ui.update_address_bar(address)
        self.ctx.ui.connect_button_action(None)

    def _cmd_disconnect(self):
        """Disconnect from the room."""
        asyncio.create_task(self.ctx.disconnect())

    def _cmd_exit(self):
        """Close the client."""
        self.ctx.ui.stop()


class BotWContext(CommonContext):
    command_processor = BotWCommands

    def __init__(self, executable, windows):
        super().__init__()
        self.executable = executable
        self.windows = windows
        self.cemu = None
        self.process = None
        self.connection_task = None
        self.tracker_url = None
        self.server_version = ()
        self.stop_requested = False

    def ensure_game(self):
        if self.cemu is not None and self.cemu.poll() is None:
            return True
        try:
            self.cemu = launch_cemu(self.windows)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.error("Could not launch Cemu: %s", exc)
            return False
        if self.cemu is None:
            logger.info("Select the Cemu executable to connect.")
            return False
        logger.info("Load your save in Cemu with the seed pack enabled.")
        return True

    async def start_bridge(self, address, player, password, tracker):
        self.server_address = address
        command = [str(self.executable), "--launcher", "--verbose", "--server", address, "--slot", player]
        if tracker:
            command.extend(("--tracker", "--tracker-port", "0"))
        environment = dict(env_cleared_lib_path())
        environment["BOTWAP_ROOM_PASSWORD"] = password
        try:
            if self.cemu is None or self.cemu.poll() is not None:
                logger.info("Open the game in Cemu before connecting.")
                return
            command.extend(("--cemu-pid", str(self.cemu.pid)))
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if self.windows else {}
            memory_fd = None
            try:
                if not self.windows:
                    # The window owns Cemu. Hand the bridge the open handle to this
                    # child so Linux can keep its default process tracing policy.
                    memory_fd = os.open(f"/proc/{self.cemu.pid}/mem", os.O_RDWR)
                    command.extend(("--cemu-mem-fd", str(memory_fd)))
                    options["pass_fds"] = (memory_fd,)
                self.process = await asyncio.create_subprocess_exec(
                    *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT, env=environment,
                    limit=1024 * 1024, **options,
                )
            finally:
                if memory_fd is not None:
                    os.close(memory_fd)
            if self.stop_requested:
                self.process.stdin.close()
            connected_once = False
            async for raw in self.process.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line.startswith("@BOTWAP@"):
                    event = json.loads(line[8:])
                    if event["type"] == "hints":
                        self.ui.show_hints(event["hints"])
                    elif event["type"] == "message":
                        logger.info("%s", event["text"].replace(password, "[redacted]") if password else event["text"])
                    continue
                if line.startswith("Connected to AP") or (connected_once and "] AP slot verified:" in line):
                    connected_once = True
                    self.server = self.process
                elif line.startswith("AP disconnected."):
                    self.server = None
                elif line.startswith("Tracker: http://127.0.0.1:"):
                    self.tracker_url = line.removeprefix("Tracker: ")
                    self.ui.tracker_address.text = self.tracker_url
                logger.info("%s", line.replace(password, "[redacted]") if password else line)
            code = await self.process.wait()
            if code:
                logger.info("BotW client exited with code %s.", code)
        except (OSError, ValueError) as exc:
            logger.error("BotW client: %s", exc)
        finally:
            if self.process is not None and self.process.returncode is None:
                await self.disconnect()
            self.process = self.server = self.tracker_url = None
            self.ui.tracker_address.text = self.ui.preview_url or ""

    async def say(self, text):
        process = self.process
        if not self.server or process is None or process.stdin.is_closing():
            logger.info("Connect before sending a message.")
            return
        try:
            process.stdin.write((text + "\n").encode())
            await process.stdin.drain()
        except OSError as exc:
            logger.info("Could not send message: %s", exc)

    async def disconnect(self, *args, **kwargs):
        self.stop_requested = True
        process = self.process
        if process is None or process.returncode is not None:
            return
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            await process.wait()

    def slot_concerns_self(self, slot):
        return False


class BotWManager(GameManager):
    base_title = "Breath of the Wild Client"

    def build(self):
        root = super().build()
        self.preview_process = None
        self.preview_url = None
        tracker = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(8))
        options = BoxLayout(size_hint_y=None, height=dp(40))
        self.tracker_enabled = MDCheckbox(size_hint=(None, None), size=(dp(40), dp(40)))
        options.add_widget(self.tracker_enabled)
        options.add_widget(MDLabel(text="Enable tracker on next connection"))
        tracker.add_widget(options)
        self.open_tracker = MDButton(MDButtonText(text="Open tracker in browser"), style="filled")
        self.open_tracker.bind(on_release=lambda *_: asyncio.create_task(self.open_tracker_in_browser()))
        tracker.add_widget(self.open_tracker)
        self.tracker_address = TextInput(readonly=True, multiline=False, size_hint_y=None, height=dp(34))
        self.tracker_address.hint_text = "Tracker address"
        tracker.add_widget(self.tracker_address)
        self.generate_map = MDButton(MDButtonText(text="Generate map"), style="filled")
        self.generate_map.bind(on_release=lambda *_: asyncio.create_task(self.generate_tracker_map()))
        tracker.add_widget(self.generate_map)
        self.tracker_status = MDLabel(text="", size_hint_y=None, height=dp(60))
        tracker.add_widget(self.tracker_status)
        tracker.add_widget(BoxLayout())
        self.add_client_tab("Tracker", tracker)
        return root

    def on_start(self):
        super().on_start()
        self.ctx.ensure_game()

    async def start_tracker_preview(self):
        if self.preview_process is not None and self.preview_process.returncode is None:
            return self.preview_url
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if self.ctx.windows else {}
        self.preview_process = await asyncio.create_subprocess_exec(
            str(self.ctx.executable), "--tracker-only", "--tracker-port", "0",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env=env_cleared_lib_path(), **options,
        )
        try:
            line = await asyncio.wait_for(self.preview_process.stdout.readline(), timeout=10)
        except asyncio.TimeoutError:
            if self.preview_process.returncode is None:
                self.preview_process.kill()
                await self.preview_process.wait()
            raise OSError("The tracker preview did not start in time.") from None
        ready = line.decode(errors="replace").strip()
        if not ready.startswith("Tracker: http://127.0.0.1:"):
            raise OSError(ready or "The tracker preview exited during startup.")
        self.preview_url = ready.split()[1]
        return self.preview_url

    async def open_tracker_in_browser(self):
        self.open_tracker.disabled = True
        try:
            url = self.ctx.tracker_url or await self.start_tracker_preview()
            self.tracker_address.text = url
            if self.ctx.windows:
                os.startfile(url)
            else:
                environment = dict(env_cleared_lib_path())
                environment.pop("BROWSER", None)
                for command in (("gio", "open"), ("xdg-open",)):
                    if not shutil.which(command[0]):
                        continue
                    process = await asyncio.create_subprocess_exec(*command, url, env=environment)
                    if await process.wait() == 0:
                        break
                else:
                    raise OSError("The default browser could not be started. Copy the tracker address above.")
        except (OSError, asyncio.TimeoutError) as exc:
            self.tracker_status.text = f"Could not open tracker: {exc}"
        finally:
            self.open_tracker.disabled = False

    async def generate_tracker_map(self):
        self.generate_map.disabled = True
        try:
            settings_path = Path(user_path("BotWAP", "folders.json"))
            folders = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
            base = folders.get("base")
            update = folders.get("update")
            if not base or not (Path(base) / "UI/MapTex/MainField").is_dir():
                base = open_directory("Select the Breath of the Wild base content folder", base or "")
                update = None
            if not base:
                self.tracker_status.text = "Map generation cancelled."
                return
            self.tracker_status.text = "Generating the map from your game files…"
            patcher = await asyncio.to_thread(bundled_patcher)
            if patcher is None:
                raise RuntimeError("Install a player APWorld that includes the BotW patcher.")
            command, options = patcher
            command = [*command, "--tracker-map", "--base", base]
            if update and Path(update).is_dir():
                command.extend(("--update", update))
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options,
            )
            output, errors = await process.communicate()
            if process.returncode:
                raise RuntimeError(errors.decode(errors="replace").strip() or "Map generator exited.")
            logger.info("%s", output.decode(errors="replace").strip())
            self.tracker_status.text = "Map ready. Open or refresh the tracker."
        except (OSError, RuntimeError, ValueError) as exc:
            self.tracker_status.text = f"Could not generate the map: {exc}"
        finally:
            self.generate_map.disabled = False

    def update_texts(self, dt):
        super().update_texts(dt)
        if self.ctx.connection_task is not None and not self.ctx.connection_task.done():
            self.server_connect_button._button_text.text = "Disconnect"
            self.server_connect_bar.readonly = True

    def connect_button_action(self, button):
        if self.ctx.connection_task is not None and not self.ctx.connection_task.done():
            asyncio.create_task(self.ctx.disconnect())
            return
        address = self.server_connect_bar.text.strip().removeprefix("/connect ").strip()
        if not address:
            logger.info("Enter the Archipelago server address.")
            return
        if self.ctx.cemu is None or self.ctx.cemu.poll() is not None:
            self.ctx.ensure_game()
            return
        fields = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        player = TextInput(hint_text="Player name", text=self.ctx.username or "", multiline=False)
        password = TextInput(hint_text="Room password (optional)", multiline=False, password=True)
        connect = MDButton(MDButtonText(text="Connect"), style="filled", size_hint_y=None, height=dp(36))
        for widget in (player, password, connect):
            fields.add_widget(widget)
        dialog = Popup(title="Connect to Archipelago", content=fields, size_hint=(None, None), size=(dp(360), dp(210)))

        def submit(*_):
            if not player.text.strip():
                player.focus = True
                return
            self.ctx.username = player.text.strip()
            dialog.dismiss()
            self.show_hints([])
            self.ctx.stop_requested = False
            self.ctx.connection_task = asyncio.create_task(
                self.ctx.start_bridge(address, self.ctx.username, password.text, self.tracker_enabled.active)
            )
        for widget in (player, password):
            widget.bind(on_text_validate=submit)
        connect.bind(on_release=submit)
        dialog.open()
        player.focus = True

    def show_hints(self, hints):
        rows = [self.hint_log.header]
        for index, hint in enumerate(sorted(hints, key=lambda hint: hint["Found"])):
            status = HintStatus.HINT_FOUND if hint["Found"] else HintStatus.HINT_UNSPECIFIED
            row = {key: {"text": escape_markup(hint[key] or ("Vanilla" if key == "Entrance" else ""))}
                   for key in ("receiving", "item", "finding", "location", "Entrance")}
            row["entrance"] = row.pop("Entrance")
            row["status"] = {
                "text": self.hint_log.parser.handle_node(
                    {"type": "color", "color": status_colors[status], "text": status_names[status]}
                ),
                "hint": {"status": status, "receiving_player": -1},
            }
            row["striped"] = index % 2 == 0
            rows.append(row)
        self.hint_log.data = rows


def show_client_window(executable, windows):
    logger.setLevel(logging.INFO)

    async def run():
        context = BotWContext(executable, windows)
        context.ui = BotWManager(context)
        try:
            await context.ui.async_run()
        finally:
            if context.connection_task is not None:
                await context.disconnect()
                await context.connection_task
            preview = context.ui.preview_process
            if preview is not None and preview.returncode is None:
                try:
                    preview.terminate()
                except ProcessLookupError:
                    pass
                await preview.wait()
            context.keep_alive_task.cancel()

    asyncio.run(run())
