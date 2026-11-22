#!/usr/bin/env python3
"""Lain Companion, a small KDE desktop buddy powered by Ollama."""
from __future__ import annotations

import ast
import datetime as dt
from http.client import HTTPException
import json
from math import pi, sin
from time import monotonic
import operator
from pathlib import Path
import platform
import random
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QPushButton, QMenu, QMessageBox, QFrame, QPlainTextEdit,
)

APP_DIR = Path.home() / '.config' / 'lain-companion'
CONFIG_PATH = APP_DIR / 'config.json'
OLLAMA_URL = 'http://127.0.0.1:11434'
OLLAMA_START = ('Run ollama serve in a terminal, or start the installed service with\n'
                'sudo systemctl start ollama.service.')
DEFAULTS = {'x': None, 'y': None, 'scale': 3, 'always_on_top': True,
            'ollama_model': 'gemma3:4b'}


def load_config():
    try:
        content = json.loads(CONFIG_PATH.read_text())
        if isinstance(content, dict):
            config = {key: content.get(key, default) for key, default in DEFAULTS.items()}
            model = config['ollama_model']
            config['ollama_model'] = (model.strip() if isinstance(model, str) else '') or DEFAULTS['ollama_model']
            return config
    except (OSError, ValueError):
        pass
    return DEFAULTS.copy()


def model_setup_error(model):
    try:
        with urllib.request.urlopen(f'{OLLAMA_URL}/api/tags', timeout=2) as response:
            models = json.load(response)['models']
        if not isinstance(models, list):
            raise ValueError('Expected a model list')
    except (OSError, HTTPException, ValueError, KeyError, TypeError):
        return f'Could not read the Ollama model list at {OLLAMA_URL}.\n\n{OLLAMA_START}'

    # Ollama treats an omitted tag as :latest. Registry ports are not tags.
    installed_name = model if ':' in model.rsplit('/', 1)[-1] else f'{model}:latest'
    if not any(isinstance(entry, dict) and (
            installed_name == entry.get('name') or installed_name == entry.get('model'))
            for entry in models):
        return f'Ollama model {model} is missing.\n\nRun ollama pull {shlex.quote(model)}.'
    return None


def save_config(config):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(config, indent=2) + '\n')
    tmp.replace(CONFIG_PATH)


def rgba(hex_color):
    return QColor(hex_color)


def load_idle_sprite():
    image = QImage(str(Path(__file__).with_name('lain-idle.png')))
    if image.isNull():
        return QPixmap()

    alpha = image.convertToFormat(QImage.Format.Format_Alpha8)
    stride = alpha.bytesPerLine()
    pixels = alpha.constBits()
    left, top, right, bottom = image.width(), image.height(), 0, 0
    # Ignore alpha=1 specks when measuring the visible bounds.
    for y in range(image.height()):
        row = bytes(pixels[y * stride:y * stride + image.width()])
        row = row.replace(b'\x01', b'\x00')
        content = row.lstrip(b'\x00')
        if content:
            left = min(left, len(row) - len(content))
            right = max(right, len(row.rstrip(b'\x00')))
            top = min(top, y)
            bottom = y + 1
    if right <= left or bottom <= top:
        return QPixmap()
    return QPixmap.fromImage(image.copy(left, top, right - left, bottom - top))


def sprite_image(frame=0):
    """Draw an original 40x64 bear-hoodie pixel character (no borrowed sprites)."""
    w, h = 40, 64
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    def r(x, y, width, height, c):
        p.fillRect(x, y, width, height, rgba(c))
    ink, dark, mid, lit = '#1d171d', '#40383e', '#5e5559', '#82777a'
    # Boots and legs
    r(10, 49, 9, 12, ink); r(22, 49, 9, 12, ink)
    r(11, 50, 7, 9, dark); r(23, 50, 7, 9, dark)
    r(9, 59, 11, 3, ink); r(21, 59, 11, 3, ink)
    r(10, 60, 9, 1, mid); r(22, 60, 9, 1, mid)
    # Sleeves, hands
    r(5, 29, 7, 20, ink); r(29, 29, 7, 20, ink)
    r(6, 31, 5, 15, mid); r(30, 31, 5, 15, mid)
    r(6, 47, 5, 4, '#b98e81'); r(30, 47, 5, 4, '#b98e81')
    r(7, 47, 3, 4, '#d2aa98'); r(31, 47, 3, 4, '#d2aa98')
    # Hood & round bear ears
    r(8, 8, 8, 9, ink); r(25, 8, 8, 9, ink)
    r(10, 10, 4, 5, mid); r(27, 10, 4, 5, mid)
    r(8, 12, 25, 28, ink); r(10, 14, 21, 25, mid)
    r(12, 13, 17, 4, lit)
    # Face / hair
    r(12, 19, 17, 15, ink)
    r(13, 22, 15, 12, '#d4a796')
    r(14, 25, 13, 8, '#e1b3a2')
    r(12, 18, 17, 6, '#352a2c')
    r(13, 21, 4, 5, '#352a2c'); r(25, 21, 3, 6, '#352a2c')
    r(18, 21, 2, 5, '#493334'); r(22, 21, 2, 4, '#493334')
    # Eyes blink every few seconds
    if frame == 2:
        r(16, 28, 3, 1, '#30252a'); r(23, 28, 3, 1, '#30252a')
    else:
        r(16, 27, 2, 3, '#30252a'); r(24, 27, 2, 3, '#30252a')
        r(16, 27, 1, 1, '#f1e8e1'); r(24, 27, 1, 1, '#f1e8e1')
    r(20, 32, 2, 1, '#9a6d69')
    # Body, zipper, chest seam
    r(11, 36, 19, 18, ink); r(12, 37, 17, 16, mid)
    r(13, 37, 7, 15, dark); r(21, 37, 7, 15, '#645b5e')
    r(20, 36, 1, 18, '#c0aeaa')
    r(20, 40, 1, 1, '#f1ded2'); r(20, 45, 1, 1, '#f1ded2')
    r(14, 38, 4, 1, lit); r(24, 38, 4, 1, lit)
    # Hoodie strings
    r(16, 35, 1, 5, '#b3a6a0'); r(25, 35, 1, 5, '#b3a6a0')
    # Tiny idle variation
    if frame == 1: r(11, 44, 1, 5, lit)
    p.end()
    return img


class OllamaWorker(QThread):
    finished_text = Signal(str)
    failed_text = Signal(str)
    def __init__(self, question, model):
        super().__init__()
        self.question = question
        self.model = model

    def run(self):
        body = {
            'model': self.model,
            'stream': False,
            'options': {'num_predict': 110, 'temperature': 0.7},
            'messages': [
                {'role': 'system', 'content': (
                    'You are a tiny quiet pixel-art desktop companion called Lain. '
                    'Answer the user helpfully and accurately in their language. '
                    'Use a slightly mysterious, thoughtful tone, but do not pretend '
                    'you have access to sensors, files or tools. Keep answers under 65 words.')},
                {'role': 'user', 'content': self.question},
            ],
        }
        req = urllib.request.Request(
            f'{OLLAMA_URL}/api/chat',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=65) as response:
                result = json.load(response)
            answer = result['message']['content']
            if not isinstance(answer, str):
                raise ValueError('Expected chat text')
            answer = answer.strip()
            self.finished_text.emit(answer or 'The Wired is quiet right now.')
        except urllib.error.HTTPError as exc:
            exc.close()
            hint = (f'Run ollama pull {shlex.quote(self.model)}.'
                    if exc.code == 404 else f'Ollama returned HTTP {exc.code}.')
            self.failed_text.emit(f'Chat failed. {hint}')
        except (OSError, HTTPException):
            self.failed_text.emit('Could not reach Ollama. Run ollama serve or restart the service.')
        except (ValueError, KeyError, TypeError):
            self.failed_text.emit('Ollama returned an invalid chat response.')


BINARY_APPS = {
    'terminal': ['konsole'], 'konsole': ['konsole'],
    'files': ['dolphin'], 'file manager': ['dolphin'], 'dolphin': ['dolphin'],
    'browser': ['xdg-open', 'https://www.wikipedia.org'],
}


def safe_calculate(expression):
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
    def calc(node, depth=0):
        if depth > 12: raise ValueError('too complex')
        if isinstance(node, ast.Expression): return calc(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if abs(node.value) > 1e9: raise ValueError('number too large')
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = calc(node.operand, depth + 1)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            lhs = calc(node.left, depth + 1); rhs = calc(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(rhs) > 10: raise ValueError('exponent too large')
            result = ops[type(node.op)](lhs, rhs)
            if abs(result) > 1e12: raise ValueError('result too large')
            return result
        raise ValueError('unsupported expression')
    return calc(ast.parse(expression, mode='eval'))


def mem_info():
    values = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, rest = line.split(':', 1)
            values[key] = int(rest.strip().split()[0])
        total = values['MemTotal'] / (1024 ** 2)
        used = (values['MemTotal'] - values['MemAvailable']) / (1024 ** 2)
        return f'RAM: {used:.1f} GiB of {total:.1f} GiB in use.'
    except (OSError, ValueError, KeyError):
        return 'I could not read your RAM information.'


def local_answer(question):
    q = question.lower().strip().rstrip('?! .')
    if not q: return 'Are you there?'
    if q in ('help', 'commands', '/help', 'hilfe'):
        return ('Try: time, date, RAM, uptime, load, system, calculate 12 * 4, '
                'open terminal, open files. I use Ollama for other questions.')
    if q in ('hello', 'hi', 'hey', 'hallo', 'servus', 'lain'):
        return random.choice(['Present day... present time.', 'Hello. I am here.',
                              'Connected. What would you like to know?'])
    if q in ('time', 'what time is it', 'uhrzeit', 'wie spät ist es'):
        return 'It is ' + dt.datetime.now().strftime('%H:%M:%S') + '.'
    if q in ('date', 'today', 'datum', 'welches datum haben wir'):
        return 'Today is ' + dt.datetime.now().strftime('%A, %d %B %Y') + '.'
    if q in ('ram', 'memory', 'ram usage', 'ram auslastung', 'arbeitsspeicher') or 'how much ram' in q:
        return mem_info()
    if q in ('uptime', 'laufzeit'):
        try:
            sec = int(float(Path('/proc/uptime').read_text().split()[0]))
            days, hours, minutes = sec // 86400, (sec // 3600) % 24, (sec // 60) % 60
            return f'Your system has been awake for {days}d {hours}h {minutes}m.'
        except (OSError, ValueError): return 'I could not read the uptime.'
    if q in ('cpu', 'load', 'cpu load', 'auslastung'):
        try: return 'Load averages (1/5/15 min): ' + ' / '.join(Path('/proc/loadavg').read_text().split()[:3])
        except OSError: return 'I could not read the CPU load.'
    if q in ('system', 'os', 'linux', 'distro'):
        return f'You are using {platform.system()} {platform.release()} ({platform.machine()}).'
    if q.startswith(('calculate ', 'calc ', 'rechne ')):
        expr = q.split(' ', 1)[1]
        try: return f'{expr} = {safe_calculate(expr):g}'
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
            return 'I can calculate basic arithmetic, e.g. calculate (12 + 4) * 3.'
    if q.startswith(('open ', 'öffne ')):
        app = q.split(' ', 1)[1].strip()
        cmd = BINARY_APPS.get(app)
        if not cmd: return 'I only open approved apps: terminal, files or browser.'
        if not shutil.which(cmd[0]): return f'{cmd[0]} does not seem to be installed.'
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return f'Opening {app}.'
        except OSError: return f'I could not launch {app}.'
    return None


class Dialogue(QWidget):
    asked = Signal(str)
    def __init__(self, owner):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName('dialogue')
        self.setFixedSize(355, 224)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        panel = QFrame()
        panel.setObjectName('panel')
        outer.addWidget(panel)
        box = QVBoxLayout(panel)
        box.setContentsMargins(15, 12, 15, 12)
        box.setSpacing(9)
        top = QHBoxLayout()
        title = QLabel('LAIN // THE WIRED')
        title.setObjectName('caption')
        top.addWidget(title)
        top.addStretch()
        hide = QPushButton('×')
        hide.setFixedSize(25, 25)
        hide.setToolTip('Hide dialogue')
        hide.clicked.connect(self.hide)
        top.addWidget(hide)
        box.addLayout(top)
        self.answer = QPlainTextEdit('Present day... present time.\n\nAsk me something.')
        self.answer.setObjectName('answer')
        self.answer.setReadOnly(True)
        self.answer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        box.addWidget(self.answer, 1)
        bottom = QHBoxLayout()
        self.field = QLineEdit()
        self.field.setPlaceholderText('Write in DM_')
        self.field.returnPressed.connect(self.send_question)
        self.answer.installEventFilter(self)
        self.field.installEventFilter(self)
        bottom.addWidget(self.field, 1)
        send = QPushButton('↵')
        send.setFixedWidth(35)
        send.setToolTip('Ask Lain')
        send.clicked.connect(self.send_question)
        bottom.addWidget(send)
        box.addLayout(bottom)
        self.setStyleSheet('''
            QFrame#panel { background:#2d2339; border:3px solid #cdb96a; border-radius:3px; }
            QLabel { color:#eee4e8; border:none; background:transparent; }
            QLabel#caption { color:#e3c874; font: bold 11px monospace; }
            QPlainTextEdit#answer { color:#eee4e8; font:12px monospace;
                                    border:none; background:transparent; }
            QScrollBar:vertical { background:#241c2b; width:8px; }
            QScrollBar::handle:vertical { background:#bba85e; min-height:16px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }
            QLineEdit { color:#eee3e6; background:#15101e; border:2px solid #bba85e;
                        padding:7px; font:12px monospace; selection-background-color:#745b7e; }
            QPushButton { background:#e3c76d; color:#241c2b; border:1px solid #241c2b;
                          font: bold 15px monospace; }
            QPushButton:hover { background:#fff0a3; }
        ''')

    def eventFilter(self, watched, event):
        if watched in (self.field, self.answer) and event.type() == QEvent.Type.KeyPress:
            scrollbar = self.answer.verticalScrollBar()
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = scrollbar.singleStep()
            elif key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                step = scrollbar.pageStep()
            else:
                return super().eventFilter(watched, event)
            if key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp):
                step = -step
            scrollbar.setValue(scrollbar.value() + step)
            return True
        return super().eventFilter(watched, event)

    def send_question(self):
        question = self.field.text().strip()
        if question:
            self.field.clear()
            self.asked.emit(question)

    def show_near(self):
        screen = self.owner.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = self.owner.x() + self.owner.width() + 4
        if x + self.width() > area.right(): x = self.owner.x() - self.width() - 4
        y = self.owner.y() + self.owner.height() // 2 - self.height() // 2
        x = max(area.left(), min(x, area.right() - self.width() + 1))
        y = max(area.top(), min(y, area.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.raise_()
        self.field.setFocus()


class Companion(QWidget):
    def __init__(self, config):
        self.config = config
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self.config['always_on_top']: flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        # The companion is the main window even though it uses Qt.Tool.
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setToolTip('Lain — left-click to chat, right-click for settings, drag to move')
        self.scale = max(2, min(5, int(self.config.get('scale', 3))))
        self.frame = 0
        idle_sprite = load_idle_sprite()
        self.pixmaps = ([QPixmap.fromImage(sprite_image(i)) for i in range(3)]
                        if idle_sprite.isNull() else [idle_sprite])
        self.resize_to_sprite()
        self.drag_from = None
        self.drag_moved = False
        self.dialogue = Dialogue(self)
        self.dialogue.asked.connect(self.ask)
        self.worker = None
        startup_position = self.startup_position()
        self.move(startup_position)
        self.pending_startup_position = None
        if QApplication.platformName() == 'xcb':
            # KWin can override the position when it first maps the window.
            self.pending_startup_position = startup_position
            self.winId()
            self.windowHandle().installEventFilter(self)
        self.anim = QTimer(self)
        self.anim.timeout.connect(self.tick)
        self.animation_started = monotonic()
        self.speaking_until = 0.0
        self.anim.start(50)

    def resize_to_sprite(self):
        size = self.pixmaps[0].size().scaled(
            QSize(40 * self.scale, 64 * self.scale),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self.setFixedSize(size)

    def startup_position(self):
        x, y = self.config['x'], self.config['y']
        if type(x) is int and type(y) is int:
            # Check the integers before passing them to Qt, which uses C++ ints.
            for screen in QApplication.screens():
                area = screen.availableGeometry()
                if (area.left() - self.width() < x <= area.right()
                        and area.top() - self.height() < y <= area.bottom()):
                    return QPoint(x, y)

        area = QApplication.primaryScreen().availableGeometry()
        return QPoint(
            max(area.left(), area.x() + area.width() - self.width() - 48),
            max(area.top(), area.y() + area.height() - self.height() - 36),
        )

    def eventFilter(self, watched, event):
        if (self.pending_startup_position is not None
                and event.type() == QEvent.Type.Expose and watched.isExposed()):
            position = self.pending_startup_position
            self.pending_startup_position = None
            watched.removeEventFilter(self)
            self.move(position)
        return super().eventFilter(watched, event)

    def tick(self):
        if len(self.pixmaps) > 1:
            elapsed = monotonic() - self.animation_started
            self.frame = 2 if elapsed % 5.5 < 0.15 and elapsed >= 5.5 else int(elapsed % 4 >= 2)
        self.update()

    def paintEvent(self, _):
        now = monotonic()
        elapsed = now - self.animation_started
        phase = 2 * pi * elapsed
        # Keep the feet anchored and leave the window geometry fixed.
        lift = (1 - sin(phase / 4)) / 2
        if self.dialogue.isVisible():
            if now < self.speaking_until:
                lift = 2 * (1 - sin(phase * 2.3))
            elif self.worker is not None:
                lift = 1 - sin(phase / 1.8)
        rect = self.rect().adjusted(0, round(lift * self.scale / 3), 0, 0)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(rect, self.pixmaps[self.frame])
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_from = event.globalPosition().toPoint() - self.pos()
            self.drag_moved = False
            event.accept()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton) and self.drag_from is not None:
            new_pos = event.globalPosition().toPoint() - self.drag_from
            if (new_pos - self.pos()).manhattanLength() > 2: self.drag_moved = True
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drag_moved:
                self.config.update(x=self.x(), y=self.y())
                save_config(self.config)
                if self.dialogue.isVisible(): self.dialogue.show_near()
            elif self.dialogue.isVisible(): self.dialogue.hide()
            else: self.dialogue.show_near()
            self.drag_from = None
            event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction('Chat with Lain', self.dialogue.show_near)
        menu.addSeparator()
        menu.addAction('Set Ollama model…', self.set_model)
        menu.addSeparator()
        size_menu = menu.addMenu('Sprite size')
        for scale in (2, 3, 4, 5):
            a = size_menu.addAction(f'{scale}×')
            a.setCheckable(True)
            a.setChecked(scale == self.scale)
            a.triggered.connect(lambda checked=False, s=scale: self.set_scale(s))
        menu.addSeparator()
        menu.addAction('Quit', QApplication.instance().quit)
        menu.exec(event.globalPos())

    def set_model(self):
        from PySide6.QtWidgets import QInputDialog
        model, ok = QInputDialog.getText(self, 'Ollama model', 'Installed model name:',
                                         text=self.config['ollama_model'])
        model = model.strip()
        if not ok or not model:
            return
        error = model_setup_error(model)
        if error:
            show_setup_error(error, self)
            return
        self.config['ollama_model'] = model
        save_config(self.config)

    def set_scale(self, scale):
        self.scale = scale
        self.config['scale'] = scale
        save_config(self.config)
        self.resize_to_sprite()
        self.update()
        if self.dialogue.isVisible(): self.dialogue.show_near()

    def ask(self, question):
        response = local_answer(question)
        if response is not None:
            self.show_reply(response)
            return
        if self.worker is not None:
            self.dialogue.answer.setPlainText('Still thinking about your last question…')
            self.dialogue.field.setText(question)
            return
        self.speaking_until = 0.0
        self.dialogue.answer.setPlainText('Connecting to the Wired…')
        self.worker = OllamaWorker(question, self.config['ollama_model'])
        self.worker.finished_text.connect(self.show_reply)
        self.worker.failed_text.connect(self.show_chat_error)
        self.worker.finished.connect(self.chat_finished)
        self.worker.start()

    def show_reply(self, response):
        self.dialogue.answer.setPlainText(response)
        self.dialogue.answer.verticalScrollBar().setValue(0)
        duration = min(5.0, max(1.1, len(response.split()) / 4))
        self.speaking_until = monotonic() + duration if self.dialogue.isVisible() else 0.0
        self.update()

    def show_chat_error(self, error):
        self.speaking_until = 0.0
        if not self.dialogue.field.text():
            self.dialogue.field.setText(self.worker.question)
            self.dialogue.answer.setPlainText(f'{error}\nPress Enter to retry.')
        else:
            self.dialogue.answer.setPlainText(f'{error}\nResend your question to retry.')

    def chat_finished(self):
        self.worker.deleteLater()
        self.worker = None

    def closeEvent(self, event):
        self.dialogue.close()
        super().closeEvent(event)


def show_setup_error(error, parent=None):
    dialog = QMessageBox(QMessageBox.Icon.Critical, 'Ollama setup', error, parent=parent)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.exec()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Lain Companion')
    app.setQuitOnLastWindowClosed(True)
    config = load_config()
    error = model_setup_error(config['ollama_model'])
    if error:
        print(error, file=sys.stderr)
        show_setup_error(error)
        return 1
    buddy = Companion(config)
    buddy.show()
    status = app.exec()
    if buddy.worker is not None:
        buddy.worker.wait()
    return status


if __name__ == '__main__':
    sys.exit(main())
