#!/usr/bin/env python3
"""Lain Companion, a KDE desktop GUI for the Codex CLI."""
from __future__ import annotations

import ast
from collections import deque
import re
import base64
from uuid import UUID
import urllib.parse
import datetime as dt
from http.client import HTTPException
import json
from math import pi, sin
from time import monotonic
import os
import tempfile
import stat
import operator
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from PySide6.QtCore import QProcess, QEvent, QPoint, QSize, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QSizeGrip, QFileDialog, QInputDialog, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QPushButton, QMenu, QFrame, QPlainTextEdit,
)

APP_DIR = Path.home() / '.config' / 'lain-companion'
CONFIG_PATH = APP_DIR / 'config.json'
DEFAULTS = {'chat_width': 355, 'chat_height': 224, 'x': None, 'y': None, 'scale': 3, 'always_on_top': True,
            'codex_session_id': None}


def load_config():
    try:
        content = json.loads(CONFIG_PATH.read_text())
        if isinstance(content, dict):
            config = {key: content.get(key, default) for key, default in DEFAULTS.items()}
            return config
    except (OSError, ValueError):
        pass
    return DEFAULTS.copy()


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


class CodexWorker(QThread):
    finished_text = Signal(str)
    failed_text = Signal(str)

    session_ready = Signal(str)

    def __init__(self, question, session_id):
        super().__init__()
        self.question = question
        self.session_id = session_id

    def run(self):
        env = os.environ.copy()
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET'):
            env.pop(key, None)
        env['PATH'] = env.get('PATH', os.defpath) + os.pathsep + str(Path.home() / '.local/bin')
        local_cli = Path(__file__).resolve().parent / '.venv/bin/codex'
        cli = str(local_cli) if local_cli.is_file() else 'codex'
        workdir = APP_DIR / 'codex-workspace'
        args = [cli, 'exec', '--json', '--skip-git-repo-check',
                '--sandbox', 'read-only', '-c', 'forced_login_method="chatgpt"',
                '-c', 'model_provider="openai"']
        try:
            workdir.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as output_dir:
                answer_file = Path(output_dir) / 'answer.txt'
                args.extend(['--output-last-message', str(answer_file)])
                if self.session_id:
                    args.extend(['resume', str(UUID(str(self.session_id)))])
                args.append('-')
                result = subprocess.run(
                    args, cwd=workdir, env=env, text=True, capture_output=True,
                    input='Answer briefly as Lain, in the user’s language.\n\n' + self.question,
                    timeout=180, check=False)
                if result.returncode:
                    self.failed_text.emit('Codex-Anfrage fehlgeschlagen. Prüfe codex login status. '
                                          'Ist die Sitzung gelöscht, wähle im Rechtsklick-Menü „Neuer Chat“.')
                    return
                thread = None
                for line in result.stdout.splitlines():
                    if line.strip():
                        event = json.loads(line)
                        if event.get('type') == 'thread.started':
                            thread = str(UUID(event['thread_id']))
                            break
                if not thread or (self.session_id and thread != self.session_id):
                    self.failed_text.emit('Codex hat die erwartete Sitzungs-ID nicht bestätigt.')
                    return
                answer = answer_file.read_text().strip()
                if not answer:
                    self.failed_text.emit('Codex hat keine Antwort geliefert.')
                    return
                self.session_ready.emit(thread)
                self.finished_text.emit(answer)
        except (ValueError, KeyError) as exc:
            self.failed_text.emit(f'Ungültige Codex-Sitzungsdaten: {exc}. Wähle ggf. „Neuer Chat“.')
        except FileNotFoundError:
            self.failed_text.emit('Der Dienst findet codex nicht. Prüfe in Konsole: command -v codex.')
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.failed_text.emit(f'Codex: {exc}')


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
                'open terminal, open files. I use Codex for other questions.')
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


SPOTIFY_ACTIONS = {
    'play': 'play', 'pause': 'pause', 'toggle': 'play-pause',
    'next': 'next', 'weiter': 'next', 'previous': 'previous', 'zurück': 'previous',
    'status': 'status',
}


def spotify_request(question):
    text = question.strip().rstrip('?!').strip()
    q = text.casefold()
    if (re.search(r'\b(welche[rsnm]?|was|what|which)\b', q)
            and re.search(r'\b(spielt|läuft|höre|hör|playing|song|lied|track|titel)\b', q)
            and re.search(r'\b(gerade|aktuell|moment|jetzt|currently|now|playing|läuft|spielt)\b', q)):
        return 'status'
    match = re.fullmatch(r'(?:spotify\s+)?(?:spiel(?:e)?|play)\s+(.+)', text, re.I)
    if match:
        target = re.sub(r'\s+(?:auf spotify|on spotify)$', '', match[1], flags=re.I)
        return 'play ' + target
    if q == 'spotify' or q.startswith('spotify '):
        return text[7:].strip()
    return None


def resolve_track(target):
    match = re.fullmatch(
        r'(?:spotify:track:|https://open\.spotify\.com/(?:intl-[a-z]+/)?track/)'
        r'([A-Za-z0-9]{22})(?:[?#].*)?', target)
    if match:
        return 'spotify:track:' + match[1], None
    client = os.getenv('SPOTIFY_CLIENT_ID')
    secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if not client or not secret:
        raise ValueError('Für Titelsuche fehlen Spotify-API-Zugangsdaten. '
                         'Direktstart: spotify play <Spotify-Tracklink>.')
    credentials = base64.b64encode(f'{client}:{secret}'.encode()).decode()
    token_request = urllib.request.Request(
        'https://accounts.spotify.com/api/token', data=b'grant_type=client_credentials',
        headers={'Authorization': 'Basic ' + credentials})
    with urllib.request.urlopen(token_request, timeout=8) as response:
        token = json.load(response)['access_token']
    parts = re.split(r'\s+(?:von|by)\s+', target, maxsplit=1, flags=re.I)
    query = f'track:{parts[0]} artist:{parts[1]}' if len(parts) == 2 else target
    params = urllib.parse.urlencode({'q': query, 'type': 'track', 'limit': 1})
    request = urllib.request.Request('https://api.spotify.com/v1/search?' + params,
                                     headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=8) as response:
        tracks = json.load(response)['tracks']['items']
    if not tracks:
        raise ValueError('Kein passender Titel gefunden.')
    track = tracks[0]
    return track['uri'], track['name'] + ' – ' + ', '.join(a['name'] for a in track['artists'])


def spotify_command(action):
    def control(*args):
        return subprocess.run(['playerctl', '--player=spotify', *args], check=True,
                              capture_output=True, text=True, timeout=3).stdout.strip()

    try:
        if action.casefold() == 'status':
            state = control('status')
            if state == 'Stopped':
                return 'Spotify ist gestoppt.'
            info = control('metadata', '--format', '{{title}} | {{artist}}')
            label = {'Playing': 'Läuft', 'Paused': 'Pausiert'}.get(state, state)
            return f'{label}: {info}' if info.strip(' |') else f'{label}. Spotify meldet keinen Titel.'
        if action.casefold().startswith('play '):
            uri, name = resolve_track(action[5:].strip())
            control('open', uri)
            return 'An Spotify übergeben: ' + (name or uri)
        cmd = SPOTIFY_ACTIONS.get(action.casefold())
        if not cmd:
            return 'Spotify: status, play, pause, toggle, next, previous, play <Titel oder Link>.'
        control(cmd)
        return 'Spotify: ' + cmd
    except FileNotFoundError:
        return 'Installiere playerctl mit sudo pacman -S playerctl.'
    except subprocess.CalledProcessError as exc:
        return 'Spotify: ' + (exc.stderr.strip() or 'Desktop-Player nicht erreichbar.')
    except (OSError, HTTPException, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        return f'Spotify: {exc}'


class SpotifyWorker(QThread):
    finished_text = Signal(str)

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        self.finished_text.emit(spotify_command(self.action))


def edit_text_file(parent, create):
    title = 'Create text file' if create else 'Edit text file'
    choose = QFileDialog.getSaveFileName if create else QFileDialog.getOpenFileName
    filename, _ = choose(parent, title, str(Path.home()))
    if not filename:
        return 'Cancelled.'
    path = Path(filename)
    try:
        original = b''
        if not create:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
                return 'Choose a regular UTF-8 text file up to 1 MiB.'
            original = path.read_bytes()
            if b'\0' in original:
                return 'This file contains binary data.'
        elif path.exists() or path.is_symlink():
            return 'This file already exists. Use “edit file” to change it.'
        encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
        source = original.decode(encoding)
        newline = '\r\n' if '\r\n' in source else '\n'
        normalized = source.replace('\r\n', '\n')
        text, save = QInputDialog.getMultiLineText(parent, title, str(path), normalized)
        if not save:
            return 'Cancelled.'
        if not create and text == normalized:
            return 'No changes.'
        data = text.replace('\n', newline).encode(encoding)
        if create:
            with path.open('xb') as output:
                output.write(data)
        else:
            if path.is_symlink() or path.read_bytes() != original:
                return 'The file changed while open. Reopen it to edit the latest version.'
            mode = stat.S_IMODE(path.stat().st_mode)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temp = Path(output.name)
                try:
                    output.write(data)
                    output.flush()
                    os.fchmod(output.fileno(), mode)
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
        return f'Saved {path}'
    except (OSError, UnicodeError) as exc:
        return f'File error: {exc}'


class CompanionWindow(QWidget):
    def showEvent(self, event):
        super().showEvent(event)
        if QApplication.platformName() == 'xcb' and shutil.which('wmctrl'):
            # Ask KWin after Qt maps this XWayland window.
            QTimer.singleShot(0, self.skip_taskbar)

    def skip_taskbar(self):
        if self.isVisible():
            subprocess.run(['wmctrl', '-i', '-r', hex(int(self.winId())),
                            '-b', 'add,skip_taskbar'], check=False)


class Dialogue(CompanionWindow):
    asked = Signal(str)
    def __init__(self, owner):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName('dialogue')
        self.setMinimumSize(300, 180)
        self.store_size = QTimer(self)
        self.store_size.setSingleShot(True)
        self.store_size.timeout.connect(self.save_size)
        self.resize(355, 224)
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
        upper_grip = QSizeGrip(self)
        upper_grip.setToolTip('Resize chat')
        top.addWidget(upper_grip, 0, Qt.AlignmentFlag.AlignTop)
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
        lower_grip = QSizeGrip(self)
        lower_grip.setToolTip('Resize chat')
        bottom.addWidget(lower_grip, 0, Qt.AlignmentFlag.AlignBottom)
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.store_size.start(250)

    def save_size(self):
        config = self.owner.config
        if (self.width(), self.height()) != (config['chat_width'], config['chat_height']):
            config.update(chat_width=self.width(), chat_height=self.height())
            save_config(config)

    def hideEvent(self, event):
        self.store_size.stop()
        self.save_size()
        super().hideEvent(event)

    def show_near(self):
        screen = self.owner.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if not self.isVisible():
            width = self.owner.config['chat_width']
            height = self.owner.config['chat_height']
            self.resize(min(width if type(width) is int else 355, area.width()),
                        min(height if type(height) is int else 224, area.height()))
        x = self.owner.x() + self.owner.width() + 4
        if x + self.width() > area.right(): x = self.owner.x() - self.width() - 4
        y = self.owner.y() + self.owner.height() // 2 - self.height() // 2
        x = max(area.left(), min(x, area.right() - self.width() + 1))
        y = max(area.top(), min(y, area.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.raise_()
        self.field.setFocus()


class Companion(CompanionWindow):
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
        assets = Path(__file__).resolve().parent / 'assets'
        self.poses = {name: QPixmap(str(assets / f'lain-{name}.png'))
                      for name in ('pc', 'sleep')}
        self.pose = 'stand'
        self.asleep = False
        self.question_times = deque(maxlen=3)
        self.pc_until = 0.0
        self.next_pc = monotonic() + random.uniform(90, 210)
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
        self.idle_monitor = QProcess(self)
        self.idle_monitor.readyReadStandardOutput.connect(self.read_idle_state)
        self.idle_monitor.errorOccurred.connect(
            lambda error: print(f'Lain idle monitor: {error}', file=sys.stderr))
        self.idle_monitor.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
        self.idle_monitor.start('swayidle', ['-C', '/dev/null', '-w', 'timeout', '900',
                                             'echo sleep', 'resume', 'echo awake'])
        QApplication.instance().aboutToQuit.connect(self.idle_monitor.terminate)

    def read_idle_state(self):
        while self.idle_monitor.canReadLine():
            state = bytes(self.idle_monitor.readLine()).strip()
            if state == b'sleep':
                self.asleep = True
            elif state == b'awake':
                self.asleep = False
                self.next_pc = monotonic() + random.uniform(90, 210)
        self.update_pose(monotonic())

    def update_pose(self, now):
        if self.asleep:
            pose = 'sleep'
        else:
            if now >= self.next_pc:
                self.pc_until = max(self.pc_until, now + random.uniform(15, 30))
                self.next_pc = self.pc_until + random.uniform(90, 210)
            pose = 'pc' if now < self.pc_until else 'stand'
        if pose != 'stand' and self.poses[pose].isNull():
            pose = 'stand'
        if pose != self.pose and self.drag_from is None:
            right = self.x() + self.width()
            bottom = self.y() + self.height()
            self.pose = pose
            self.resize_to_sprite()
            area = self.screen().availableGeometry()
            self.move(max(area.left(), right - self.width()), max(area.top(), bottom - self.height()))
            if self.dialogue.isVisible():
                self.dialogue.show_near()
            self.update()

    def resize_to_sprite(self):
        size = self.pixmaps[0].size().scaled(
            QSize(40 * self.scale, 64 * self.scale),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        if self.pose != 'stand':
            side = (54 if self.pose == 'pc' else 43) * self.scale
            size = self.poses[self.pose].size().scaled(QSize(side, side), Qt.AspectRatioMode.KeepAspectRatio)
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
        self.update_pose(monotonic())
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
        if self.pose == 'stand':
            p.drawPixmap(rect, self.pixmaps[self.frame])
        elif self.pose == 'sleep':
            breath = round((1 - sin(phase / 4)) * self.scale / 2)
            p.drawPixmap(self.rect().adjusted(0, breath, 0, 0), self.poses['sleep'])
        else:
            p.drawPixmap(self.rect(), self.poses['pc'])
            # A line grows on the CRT as Lain types, followed by a blinking cursor.
            x, y = round(self.width() * .625), round(self.height() * .32)
            length = int(elapsed * 6) % 11
            dot = max(1, self.scale // 2)
            p.fillRect(x, y, length * dot, dot, QColor('#b5e7a5'))
            if int(elapsed * 2) % 2 == 0:
                p.fillRect(x + (length + 1) * dot, y, dot, dot * 2, QColor('#cfffc0'))
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
        new_chat = menu.addAction('Neuer Chat', self.new_codex_chat)
        new_chat.setEnabled(self.worker is None)
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

    def remember_codex_session(self, session_id):
        if self.config['codex_session_id'] != session_id:
            self.config['codex_session_id'] = session_id
            save_config(self.config)

    def new_codex_chat(self):
        self.remember_codex_session(None)
        self.dialogue.answer.setPlainText('Neuer Codex-Chat. Was möchtest du wissen?')
        self.dialogue.show_near()

    def set_scale(self, scale):
        self.scale = scale
        self.config['scale'] = scale
        save_config(self.config)
        self.resize_to_sprite()
        self.update()
        if self.dialogue.isVisible(): self.dialogue.show_near()

    def ask(self, question):
        now = monotonic()
        self.question_times.append(now)
        if len(self.question_times) == 3 and now - self.question_times[0] <= 120:
            self.pc_until = max(self.pc_until, now + 90)
        self.asleep = False
        self.update_pose(now)
        command = question.strip().casefold()
        action = spotify_request(question)
        if action is not None:
            if self.worker is not None:
                self.dialogue.answer.setPlainText('Bitte warte, bis die aktuelle Anfrage fertig ist.')
                self.dialogue.field.setText(question)
                return
            self.worker = SpotifyWorker(action)
            self.worker.finished_text.connect(self.show_reply)
            self.worker.finished.connect(self.chat_finished)
            self.worker.start()
            return
        if command in ('create file', 'datei erstellen', 'edit file', 'datei bearbeiten'):
            create = command in ('create file', 'datei erstellen')
            self.show_reply(edit_text_file(self.dialogue, create))
            return
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
        self.worker = CodexWorker(question, self.config['codex_session_id'])
        self.worker.session_ready.connect(self.remember_codex_session)
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


def main():
    app = QApplication(sys.argv)
    from PySide6.QtGui import QIcon
    icon = Path(__file__).resolve().parent / 'assets' / 'lain-companion-icon.png'
    app.setWindowIcon(QIcon(str(icon)))
    app.setDesktopFileName('lain-companion')
    app.setApplicationName('Lain Companion')
    app.setQuitOnLastWindowClosed(True)
    config = load_config()
    buddy = Companion(config)
    from PySide6.QtWidgets import QSystemTrayIcon
    tray = QSystemTrayIcon(app.windowIcon(), buddy)
    tray.setToolTip('Lain Companion')
    menu = QMenu(buddy)
    menu.addAction('Chat öffnen', buddy.dialogue.show_near)
    menu.addSeparator()
    menu.addAction('Lain beenden', app.quit)
    tray.setContextMenu(menu)

    def tray_clicked(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            buddy.dialogue.show_near()

    tray.activated.connect(tray_clicked)
    tray.show()
    buddy.show()
    status = app.exec()
    if buddy.worker is not None:
        buddy.worker.wait()
    return status


if __name__ == '__main__':
    sys.exit(main())
