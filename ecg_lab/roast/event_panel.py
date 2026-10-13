from __future__ import annotations

import time
from datetime import datetime

from pyqtgraph.Qt import QtCore, QtWidgets

from .events import (
    get_event_buttons,
    load_recent_events,
    load_tag_history,
    log_event,
    parse_tags,
    save_event_buttons,
    tag_prefix_at,
)

BUTTONS_PER_ROW = 4
HISTORY_ROWS = 5
PANEL_WIDTH = 600


def launch_event_panel() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = EventPanel()
    panel.setWindowTitle("Roast 事件")
    panel.setWindowFlags(panel.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    panel.show()
    app.exec_()


class TagLineEdit(QtWidgets.QLineEdit):
    """普通输入框；光标落在 #标签 里时弹出历史标签供选择。"""

    def __init__(self, tags: list[str]):
        super().__init__()
        self._model = QtCore.QStringListModel(tags)
        self._completer = QtWidgets.QCompleter(self._model, self)
        self._completer.setWidget(self)
        self._completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._completer.setFilterMode(QtCore.Qt.MatchContains)
        self._completer.activated[str].connect(self._insert_tag)
        # 候选列表弹出时按键是发给它的；我们的过滤器后装，所以先于 QCompleter 自带的处理
        self._completer.popup().installEventFilter(self)
        self.textEdited.connect(self._update_popup)

    def eventFilter(self, watched, event):
        popup = self._completer.popup()
        if watched is popup and event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            if key in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                index = popup.currentIndex()
                if key == QtCore.Qt.Key_Tab and not index.isValid():
                    # Tab 没选中任何候选时补全第一个
                    index = self._completer.completionModel().index(0, 0)
                popup.hide()
                if index.isValid():
                    self._insert_tag(index.data())
                if key != QtCore.Qt.Key_Tab:
                    # 回车：确定选中的候选（没选就保留原样），然后直接发送
                    self.returnPressed.emit()
                return True
        return super().eventFilter(watched, event)

    def add_tags(self, tags: list[str]) -> None:
        known = self._model.stringList()
        new = [tag for tag in tags if tag not in known]
        if new:
            self._model.setStringList(new + known)

    def _update_popup(self) -> None:
        found = tag_prefix_at(self.text(), self.cursorPosition())
        if found is None:
            self._completer.popup().hide()
            return
        self._completer.setCompletionPrefix(found[1])
        if self._completer.completionCount() == 0:
            self._completer.popup().hide()
            return
        self._completer.complete()

    def _insert_tag(self, tag: str) -> None:
        cursor = self.cursorPosition()
        found = tag_prefix_at(self.text(), cursor)
        if found is None:
            return
        start = found[0]
        text = self.text()
        self.setText(f"{text[:start]}#{tag} {text[cursor:].lstrip()}")
        self.setCursorPosition(start + len(tag) + 2)


class EventButton(QtWidgets.QPushButton):
    """单击发送事件，双击改按钮文字，右键改名或删除。

    双击的第一下也是一次单击，所以单击要等过了双击间隔才真正发出，
    事件时间仍然取按下的那一刻。
    """

    event_clicked = QtCore.pyqtSignal(str, float)
    rename_requested = QtCore.pyqtSignal(object)
    delete_requested = QtCore.pyqtSignal(object)

    def __init__(self, label: str):
        super().__init__(label)
        self.setToolTip("单击记录事件，双击改名，右键删除")
        self._clicked_at = 0.0
        self._double_clicked_at = 0.0
        self._single_click = QtCore.QTimer(self)
        self._single_click.setSingleShot(True)
        self._single_click.setInterval(QtWidgets.QApplication.doubleClickInterval())
        self._single_click.timeout.connect(lambda: self.event_clicked.emit(self.text(), self._clicked_at))
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        # 双击第二下松开时还会再触发一次 clicked，紧跟在双击后面的点击不算
        if time.monotonic() - self._double_clicked_at < self._single_click.interval() / 1000:
            return
        self._clicked_at = time.time()
        self._single_click.start()

    def mouseDoubleClickEvent(self, event) -> None:
        self._single_click.stop()
        self._double_clicked_at = time.monotonic()
        super().mouseDoubleClickEvent(event)
        # 等这次鼠标事件处理完再弹对话框，否则按钮收不到松开事件
        QtCore.QTimer.singleShot(0, lambda: self.rename_requested.emit(self))

    def contextMenuEvent(self, event) -> None:
        menu = QtWidgets.QMenu(self)
        rename = menu.addAction("改名")
        delete = menu.addAction("删除")
        chosen = menu.exec_(event.globalPos())
        if chosen is rename:
            self.rename_requested.emit(self)
        elif chosen is delete:
            self.delete_requested.emit(self)


class EventPanel(QtWidgets.QWidget):
    """事件面板：输入框 + 快捷事件按钮 + 最近几条记录，发送时带上当前时间写进吐槽上下文。"""

    # 按钮增删导致面板高度变化时发出，外层窗口据此重新固定大小
    resized = QtCore.pyqtSignal()

    def __init__(self, context_provider=None, directory=None):
        super().__init__()
        self._context_provider = context_provider
        self._directory = directory

        labels = get_event_buttons(directory)
        # 用过的标签按次数排在前面，没用过的按钮标签垫底
        history = load_tag_history(directory)
        self.input = TagLineEdit(history + [label for label in labels if label not in history])
        self.input.setPlaceholderText("发生了什么？# 打标签，Tab 补全，回车发送")
        self.input.returnPressed.connect(self.send_input)
        send_button = QtWidgets.QPushButton("发送")
        send_button.clicked.connect(self.send_input)

        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(send_button)

        self.buttons = [self._make_button(label) for label in labels]
        self.add_button = QtWidgets.QPushButton("+")
        self.add_button.setToolTip("添加事件按钮")
        self.add_button.clicked.connect(self.add_event_button)
        self._button_grid = QtWidgets.QGridLayout()

        self.history = QtWidgets.QListWidget()
        self.history.setFocusPolicy(QtCore.Qt.NoFocus)
        self.history.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.history.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.history.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.history.setTextElideMode(QtCore.Qt.ElideRight)
        self.history.setStyleSheet("color: gray;")
        row_height = self.history.fontMetrics().height() + 4
        self.history.setFixedHeight(HISTORY_ROWS * row_height + 2 * self.history.frameWidth())
        for record in load_recent_events(HISTORY_ROWS, directory):
            self._show_in_history(f"{datetime.fromisoformat(record['ts']):%H:%M:%S} {record['text']}")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(input_row)
        layout.addLayout(self._button_grid)
        layout.addWidget(self.history)
        self._layout_buttons()

    def _make_button(self, label: str) -> EventButton:
        button = EventButton(label)
        button.event_clicked.connect(self.send_button_event)
        button.rename_requested.connect(self.rename_button)
        button.delete_requested.connect(self.delete_button)
        return button

    def _layout_buttons(self) -> None:
        """按当前按钮列表重排网格（加号永远在最后），并按新的行数重新固定面板大小"""
        while self._button_grid.count():
            self._button_grid.takeAt(0)
        for index, button in enumerate([*self.buttons, self.add_button]):
            self._button_grid.addWidget(button, index // BUTTONS_PER_ROW, index % BUTTONS_PER_ROW)
        self.layout().activate()
        self.setFixedSize(PANEL_WIDTH, self.sizeHint().height())
        self.resized.emit()

    def _save_buttons(self) -> None:
        try:
            save_event_buttons([button.text() for button in self.buttons], self._directory)
        except OSError as exc:
            self._show_in_history(f"按钮没存上：{exc}")

    def add_event_button(self) -> None:
        text, accepted = QtWidgets.QInputDialog.getText(self, "添加事件按钮", "按钮文字（也是它的标签）：")
        label = text.strip().lstrip("#")
        if not accepted or not label or label in [button.text() for button in self.buttons]:
            return
        self.buttons.append(self._make_button(label))
        self.input.add_tags([label])
        self._layout_buttons()
        self._save_buttons()

    def delete_button(self, button: EventButton) -> None:
        self.buttons.remove(button)
        button.setParent(None)
        button.deleteLater()
        self._layout_buttons()
        self._save_buttons()

    def _show_in_history(self, line: str) -> None:
        # 最新的在最上面，只留 HISTORY_ROWS 条
        self.history.insertItem(0, line)
        while self.history.count() > HISTORY_ROWS:
            self.history.takeItem(self.history.count() - 1)

    def send_input(self) -> None:
        self._send(self.input.text(), "input", time.time())

    def send_button_event(self, label: str, clicked_at: float) -> None:
        # 输入框里已有的文字当作这次事件的备注一起发出去
        self._send(f"#{label} {self.input.text()}", "button", clicked_at)

    def rename_button(self, button: EventButton) -> None:
        text, accepted = QtWidgets.QInputDialog.getText(
            self, "修改事件按钮", "按钮文字（也是它的标签）：", text=button.text()
        )
        label = text.strip().lstrip("#")
        if not accepted or not label or label == button.text():
            return
        button.setText(label)
        self.input.add_tags([label])
        self._save_buttons()

    def _send(self, text: str, source: str, now: float) -> None:
        context = self._context_provider() if self._context_provider is not None else None
        try:
            record = log_event(text, now, source=source, context=context, directory=self._directory)
        except OSError as exc:
            self._show_in_history(f"写入失败：{exc}")
            return
        if record is None:
            return

        self.input.clear()
        self.input.add_tags(parse_tags(record["text"]))
        stamp = time.strftime("%H:%M:%S", time.localtime(now))
        self._show_in_history(f"{stamp} {record['text']}")
        print(f"[{stamp}] 事件：{record['text']}", flush=True)
