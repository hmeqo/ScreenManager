from enum import Enum, auto
import re
import os
import pathlib
import multiprocessing

from textual.app import App
from textual.reactive import reactive
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Label, Button, Input, Pretty

DIR = pathlib.Path(__file__).parent
pattern_ls = re.compile(r"\s+(.+?)\s+\((.+?)\)\s+\((.+?)\)")


def run_on_newprocess(command: str):
    """在新的进程中执行命令"""
    multiprocessing.set_start_method("spawn")
    multiprocessing.Process(
        target=os.system,
        args=(command,)
    ).start()


class ScreenItem(Static):
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
            run_on_newprocess(f"screen -r {self.serial}")


class ScreenViewFields(Container):
    """Screen视图字段"""

    def compose(self):
        yield Label("序列号")
        yield Label("创建时间")
        yield Label("Info")
        yield Label("", classes="screenviewfields-btns")
        yield Label("", classes="screenviewfields-btns")


class ScreenView(Container):
    """Screen视图"""

    def compose(self):
        yield Label("正在运行的终端", id="screenview-title")
        yield ScreenViewFields()

    def add(self, serial: str, date: str, info: str):
        self.mount(ScreenItem(serial, date, info))

    def clear(self):
        for i in self.query(ScreenItem):
            i.remove()


class PopenLog(Container):
    """日志"""

    curline = reactive(Horizontal(classes="code-line"))

    def on_mount(self):
        self.mount(self.curline)

    def newline(self):
        """创建新行"""
        line = Horizontal(classes="code-line")
        self.mount(line)
        self.curline = line
        # 延迟设置滚动条位置
        self.timer = self.set_interval(0.1, self.update)

    def write_command(self, text: str):
        """写入命令"""
        self.curline.mount(Label("$", classes="code-com code-cmdsign"))
        self.curline.mount(Label(text, classes="code-cmd"))
        self.newline()

    def write(self, text: str):
        """输出日志"""
        lines = text.splitlines()
        if lines:
            lasttext = lines.pop()
            for i in lines:
                self.curline.mount(Label(i))
                self.newline()
            self.curline.mount(Label(lasttext))
            if text.endswith(os.linesep):
                self.newline()

    async def update(self):
        self.scroll_to(0, self.max_scroll_y, animate=False)
        await self.timer.stop()


class PopenExec(Container):
    """执行命令以及左侧输出界面"""

    def compose(self):
        yield Label("输出")
        yield Container(PopenLog())

    def exec(self, command: str):
        """执行命令并记录, 返回本次命令的文本"""
        logger = self.query_one(PopenLog)
        logger.write_command(command)
        with os.popen(command) as p:
            res = p.read()
        logger.write(res)
        return res


class PanelTerminalName(Input):
    """终端名输入框"""


class PanelCommand(Input):
    """命令输入框"""


class Panel(Container):
    """右侧面板"""

    def compose(self):
        # 判断拥有可执行权的文件, 并设为默认命令
        command = ""
        for path in os.listdir():
            try:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    command = f"./{path}"
                    break
            except OSError:
                pass

        yield PanelTerminalName(placeholder="终端名")
        yield PanelCommand(command, placeholder="命令")
        yield Button("添加终端", variant="success", id="panel-add")

    def on_button_pressed(self, event: Button.Pressed):
        cmd_text = "screen"
        if event.button.id == "panel-add":
            # 如果输入了命令则直接执行命令，否则退出再执行命令
            name = self.query_one(PanelTerminalName).value
            command = self.query_one(PanelCommand).value
            if name:
                cmd_text = f"{cmd_text} -S {name}"
            if command:
                cmd_text = f"{cmd_text} {command}"
            self.app.exit()
            run_on_newprocess(cmd_text)


class MainContainer(Container):
    """主容器"""

    def compose(self):
        yield ScreenView()
        yield PopenExec()
        yield Panel()


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
        yield Footer()
        yield MainContainer(classes="viewmode-screens")

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
            self.query_one(MainContainer).remove_class("viewmode-screens")
            self.query_one(MainContainer).add_class("viewmode-output")
        elif self.viewmode == ViewModes.OUTPUT:
            self.viewmode = ViewModes.SCREENS
            self.query_one(MainContainer).remove_class("viewmode-output")
            self.query_one(MainContainer).add_class("viewmode-screens")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = ScreenManager(watch_css=True)
    app.run()
