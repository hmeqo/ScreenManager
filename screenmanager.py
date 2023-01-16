from enum import Enum, auto
import re
import os
from pathlib import Path
import multiprocessing
import subprocess
import sys

from rich.syntax import Syntax
from textual.app import App
from textual.reactive import reactive
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Label, Button, Input, Pretty

DIR = Path(__file__).parent
pattern_ls = re.compile(r"\s+(.+?)\s+\((.+?)\)\s+\((.+?)\)")


def _run_on_newprocess(commands: list):
    subprocess.Popen(commands).wait()
    os.execlp(sys.executable, sys.executable, __file__)


def run_on_newprocess(commands: list):
    """在新的进程中执行命令"""
    multiprocessing.set_start_method("spawn")
    multiprocessing.Process(
        target=_run_on_newprocess,
        args=(commands,)
    ).start()


class ScreenItem(Horizontal):
    """Screen视图行"""

    def __init__(self, serial: str, date: str, info: str):
        super().__init__(classes="screeninfo")
        self.serial = serial
        self.date = date
        self.info = info

    def compose(self):
        yield Pretty(self.serial)
        yield Label(self.date)
        yield Label(self.info)
        yield Button("进入", id="screenitem-into", classes="screenitem-btns")
        yield Button("终止", id="screenitem-terminal", classes="screenitem-btns")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "screenitem-terminal":
            command = f"screen -X -S {self.serial} quit"
            self.app.query_one(PopenExec).exec(command)
            self.remove()
        elif event.button.id == "screenitem-into":
            self.app.exit()
            run_on_newprocess(["screen", "-r", self.serial])


class ScreenView(Container):
    """Screen视图"""

    def compose(self):
        yield Label("正在运行的终端", id="screenview-title")
        yield Horizontal(
            Label("序列号"),
            Label("创建时间"),
            Label("连接状态"),
            Label("", classes="screenviewfields-btns"),
            Label("", classes="screenviewfields-btns"),
            id="screenviewfields"
        )

    def add(self, serial: str, date: str, info: str):
        self.mount(ScreenItem(serial, date, info))

    def clear(self):
        for i in self.query(ScreenItem):
            i.remove()


class PopenExec(Container):
    """执行命令以及左侧输出界面"""

    text = reactive("")

    def __init__(self):
        super().__init__()
        self.logger = Static(expand=True)

    def compose(self):
        yield Label("输出")
        yield Container(self.logger, id="log-container")

    def exec(self, command: str):
        """执行命令并记录, 返回本次命令的文本"""
        text = f"> {command}\n"
        with os.popen(command) as p:
            res = p.read()
        text = text + res
        self.text += text
        self.update(self.text)
        return res

    def update(self, text: str):
        """写入文本"""
        try:
            syntax = Syntax(
                text,
                "bash",
                theme="github-dark",
            )
        except Exception as e:
            self.logger.update(str(e))
        else:
            self.logger.update(syntax)
            # 延迟设置滚动条位置
            self.timer = self.set_interval(0.1, self.update_scroll)

    async def update_scroll(self):
            self.query_one("#log-container").scroll_end(animate=False)
            await self.timer.stop()

    def clear(self):
        """清空"""
        self.text = ""
        self.query_one(Static).update()


class Panel(Container):
    """右侧面板"""

    def __init__(self):
        super().__init__()
        # 判断拥有可执行权的文件, 并设为默认命令
        command = ""
        for path in os.listdir():
            try:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    command = f"./{path}"
                    break
            except OSError:
                pass
        self.input_terminal = Input(placeholder="终端名")
        self.input_command = Input(command, placeholder="命令")

    def compose(self):

        yield self.input_terminal
        yield self.input_command
        yield Button("添加终端", id="panel-add")

    def on_button_pressed(self, event: Button.Pressed):
        commands = ["screen"]
        if event.button.id == "panel-add":
            name = self.input_terminal.value
            command = self.input_command.value
            if name:
                commands += ["-S", name]
            if command:
                commands.append(command)
            self.app.exit()
            run_on_newprocess(commands)


class ViewModes(Enum):
    """视图模式"""

    SCREENS = auto()
    OUTPUT = auto()


class ScreenManager(App):
    """Main app"""

    CSS_PATH = DIR.joinpath("screenmanager.css")
    BINDINGS = [
        ("d", "toggle_dark", "切换深/浅色模式"),
        ("r", "refresh", "刷新"),
        ("v", "switch_view", "切换视图"),
        ("q", "quit", "退出"),
    ]
    viewmode = ViewModes.SCREENS

    def compose(self):
        yield Header(True)
        yield Horizontal(
            ScreenView(),
            PopenExec(),
            Panel(),
            id="main-container",
        )
        yield Footer()

    def on_mount(self):
        self.action_refresh()

    def action_refresh(self):
        """刷新 ScreenView"""
        sv = self.query_one(ScreenView)
        sv.clear()
        for i in re.findall(pattern_ls, self.query_one(PopenExec).exec("screen -ls")):
            sv.add(*i)

    def action_switch_view(self):
        """切换视图模式"""
        if self.viewmode == ViewModes.SCREENS:
            self.viewmode = ViewModes.OUTPUT
            self.query_one(ScreenView).styles.display = "none"
            self.query_one(PopenExec).styles.display = "block"
        elif self.viewmode == ViewModes.OUTPUT:
            self.viewmode = ViewModes.SCREENS
            self.query_one(ScreenView).styles.display = "block"
            self.query_one(PopenExec).styles.display = "none"


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = ScreenManager(watch_css=True)
    app.run()
