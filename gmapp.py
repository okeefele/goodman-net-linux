#!/usr/bin/env python3
"""GoodMan Net — десктоп-клиент. Нативное GTK-приложение (Linux), web-UI fallback (Windows).

Запуск: goodman-net (или python3 gmapp.py). Никаких браузеров: окно — GTK3,
VPN (tun) поднимает системный сервис goodman-net (через systemd + polkit, без пароля).
"""
import json, os, sys, threading, subprocess, urllib.request, platform

import gmcore

IS_WIN = platform.system() == 'Windows'
# ресурсы (ui.html, logo, sing-box, wintun): рядом со скриптом, а в PyInstaller-сборке — в _MEIPASS
if getattr(sys, 'frozen', False):
    RES_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(sys.executable)
else:
    RES_DIR = APP_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_HOME = os.path.join(os.path.expanduser('~'), '.config', 'goodman-net')
SETTINGS = os.path.join(CFG_HOME, 'settings.json')
SYS_CONFIG = (os.path.join(os.environ.get('PROGRAMDATA', 'C:/ProgramData'), 'GoodManNet', 'config.json')
              if IS_WIN else '/etc/goodman-net/config.json')
SING_BOX = (os.path.join(RES_DIR, 'sing-box.exe') if IS_WIN else os.path.join(RES_DIR, 'sing-box'))
KILL_ENV = '/etc/goodman-net/killswitch.env'

os.makedirs(CFG_HOME, exist_ok=True)

# Windows (--noconsole): stdout/stderr = None или cp1252 → print с кириллицей падает.
# Перенаправляем весь вывод в лог-файл utf-8; гарантируем, что потоки НИКОГДА не None.
if IS_WIN:
    import io as _io
    _lf = None
    for _d in (os.path.dirname(SYS_CONFIG),
               os.path.join(os.environ.get('LOCALAPPDATA', ''), 'GoodManNet'),
               os.environ.get('TEMP', '')):
        try:
            if not _d:
                continue
            os.makedirs(_d, exist_ok=True)
            _lf = open(os.path.join(_d, 'app.log'), 'a', encoding='utf-8', errors='replace', buffering=1)
            break
        except Exception:
            _lf = None
    if _lf is None:
        _lf = _io.StringIO()          # крайний случай — лишь бы не None
    sys.stdout = _lf
    sys.stderr = _lf

import uuid as _uuid

FLAGS = {'GB': '🇬🇧', 'DE': '🇩🇪', 'PL': '🇵🇱', 'IT': '🇮🇹', 'CA': '🇨🇦', 'US': '🇺🇸',
         'JP': '🇯🇵', 'KZ': '🇰🇿', 'TR': '🇹🇷', 'NL': '🇳🇱', 'IR': '🇮🇷', 'RU': '🇷🇺'}

# ---------------- локализация ----------------
L10N = {
    'ru': {
        'disconnected': 'Отключено', 'connected': 'Подключено', 'connecting': 'Подключение…',
        'disconnecting': 'Отключение…', 'switching': 'Переключение…', 'sub_loading': 'Загрузка подписки…',
        'sub_updating': 'Обновление подписки…', 'add_sub_hint': 'Добавьте подписку, чтобы начать',
        'lk': 'Личный кабинет', 'open_lk': 'Открыть личный кабинет',
        'sub_placeholder': 'Ссылка на подписку (gdman.ink/s/...)', 'sub_add': 'Подключить подписку',
        'error': 'Ошибка', 'copy_error': '📋 Скопировать ошибку',
        'menu_refresh': '🔄 Обновить подписку', 'menu_change': '🔗 Сменить подписку',
        'menu_logout': '🚪 Выйти из подписки', 'menu_logs': '📋 Логи VPN-сервиса',
        'qa_refresh': '🔄 Обновить', 'qa_bypass': '📱 Мимо VPN', 'qa_kill': '🛡 Kill switch',
        'qa_speed': '📊 Скорость', 'speed_title': 'Скорость соединения',
        'speed_run': 'Измеряю скорость…', 'speed_off': 'Сначала подключитесь',
        'tg': '✈ Telegram',
        'menu_kill': '🛡 Kill Switch (блокировать интернет без VPN)',
        'menu_bypass': '🏦 Сайты .ru/.рф — мимо VPN',
        'menu_theme': '🌓 Светлая тема', 'menu_lang': '🌐 English',
        'logout_q': 'Выйти из подписки?',
        'logout_msg': 'VPN будет отключён, подписка удалена из приложения. '
                      'Саму подписку это не отменяет — её можно добавить снова.',
        'logs_title': 'Логи VPN-сервиса — GoodMan Net', 'logs_refresh': '🔄 Обновить',
        'logs_copy': '📋 Скопировать всё', 'loading': 'Загрузка…',
        'err_no_sub': 'Сначала добавьте подписку',
        'err_other_vpn': 'Сначала отключите другой VPN',
        'err_other_vpn_d': 'Обнаружен активный VPN-интерфейс «%s» (похоже, Happ или другой клиент).\n'
                           'Два VPN одновременно ломают интернет: отключите соединение в том приложении '
                           '(или закройте его) и нажмите кнопку ещё раз.',
        'err_cfg': 'Ошибка конфигурации VPN', 'err_start': 'Не удалось запустить VPN-сервис',
        'err_notup': 'VPN-сервис не стартовал', 'err_sub_load': 'Не удалось загрузить подписку',
        'err_sub_upd': 'Не удалось обновить подписку', 'err_sub_empty': 'Подписка пуста или неверная ссылка',
        'err_app': 'Внутренняя ошибка приложения',
        'err_kill': 'Kill Switch недоступен',
        'err_kill_d': 'Нужна свежая установка. Выполните в терминале:\n'
                      'wget -qO- https://gdman.ink/dl/install.sh | sudo bash',
        'tt_menu': 'Меню', 'tt_logs': 'Логи VPN-сервиса', 'tt_power': 'Подключить/отключить',
    },
    'en': {
        'disconnected': 'Disconnected', 'connected': 'Connected', 'connecting': 'Connecting…',
        'disconnecting': 'Disconnecting…', 'switching': 'Switching…', 'sub_loading': 'Loading subscription…',
        'sub_updating': 'Updating subscription…', 'add_sub_hint': 'Add a subscription to start',
        'lk': 'Account', 'open_lk': 'Open account page',
        'sub_placeholder': 'Subscription link (gdman.ink/s/...)', 'sub_add': 'Add subscription',
        'error': 'Error', 'copy_error': '📋 Copy error',
        'menu_refresh': '🔄 Refresh subscription', 'menu_change': '🔗 Change subscription',
        'menu_logout': '🚪 Log out of subscription', 'menu_logs': '📋 VPN service logs',
        'qa_refresh': '🔄 Refresh', 'qa_bypass': '📱 Bypass VPN', 'qa_kill': '🛡 Kill switch',
        'qa_speed': '📊 Speed', 'speed_title': 'Connection speed',
        'speed_run': 'Measuring speed…', 'speed_off': 'Connect first',
        'tg': '✈ Telegram',
        'menu_kill': '🛡 Kill Switch (block internet without VPN)',
        'menu_bypass': '🏦 .ru/.рф sites — bypass VPN',
        'menu_theme': '🌓 Light theme', 'menu_lang': '🌐 Русский',
        'logout_q': 'Log out of subscription?',
        'logout_msg': 'VPN will be disconnected and the subscription removed from the app. '
                      'The subscription itself stays valid — you can add it again.',
        'logs_title': 'VPN service logs — GoodMan Net', 'logs_refresh': '🔄 Refresh',
        'logs_copy': '📋 Copy all', 'loading': 'Loading…',
        'err_no_sub': 'Add a subscription first',
        'err_other_vpn': 'Disconnect the other VPN first',
        'err_other_vpn_d': 'Active VPN interface “%s” detected (looks like Happ or another client).\n'
                           'Two VPNs at once break the internet: disconnect it there and press the button again.',
        'err_cfg': 'VPN configuration error', 'err_start': 'Failed to start VPN service',
        'err_notup': 'VPN service did not start', 'err_sub_load': 'Failed to load subscription',
        'err_sub_upd': 'Failed to refresh subscription', 'err_sub_empty': 'Subscription is empty or link is wrong',
        'err_app': 'Internal application error',
        'err_kill': 'Kill Switch unavailable',
        'err_kill_d': 'A fresh install is required. Run in terminal:\n'
                      'wget -qO- https://gdman.ink/dl/install.sh | sudo bash',
        'tt_menu': 'Menu', 'tt_logs': 'VPN service logs', 'tt_power': 'Connect/disconnect',
    },
}


def fmt_bytes(n):
    n = float(n or 0)
    for unit in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if n < 1024 or unit == 'ТБ':
            return ('%.0f %s' % (n, unit)) if unit in ('Б', 'КБ') else ('%.1f %s' % (n, unit))
        n /= 1024
    return '%.1f ТБ' % n


def cap_first(s):
    s = (s or '').strip()
    return s[:1].upper() + s[1:] if s else s


def load_settings():
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except Exception:
        return {'sub': '', 'servers': [], 'selected': 0}


def save_settings(s):
    json.dump(s, open(SETTINGS, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


def tr(key):
    lang = load_settings().get('lang', 'ru')
    return L10N.get(lang, L10N['ru']).get(key, key)


def get_hwid():
    st = load_settings()
    if not st.get('hwid'):
        st['hwid'] = _uuid.uuid4().hex + _uuid.uuid4().hex[:8]
        save_settings(st)
    return st['hwid']


def sub_fetch(url):
    """Загрузка подписки с hwid. Возвращает (servers, error, meta)."""
    osn = 'windows' if IS_WIN else 'linux'
    try:
        model = platform.node()[:40]
    except Exception:
        model = 'Desktop'
    servers, meta = gmcore.fetch_subscription(url, hwid=get_hwid(), os_name=osn, model=model)
    real = [s for s in servers if s.get('uuid') and set(s['uuid'].replace('-', '')) != {'0'}]
    if servers and not real:
        return [], servers[0]['name'].strip(), meta   # текст предупреждения от сервера
    return real, '', meta


def apply_sub(url, servers, meta, st=None):
    """Сохранить подписку + мету (ЛК, announce) в настройки."""
    st = st or load_settings()
    st['sub'] = url
    st['servers'] = servers
    if st.get('selected', 0) >= len(servers):
        st['selected'] = 0
    for k in ('lk', 'account', 'announce'):
        if meta.get(k):
            st[k] = meta[k]
    if meta.get('traffic'):
        st['traffic'] = meta['traffic']
    save_settings(st)
    return st


def other_vpn_active():
    """Имя чужого VPN-интерфейса (Happ и т.п.), если он поднят. Иначе None."""
    if IS_WIN:
        return None
    try:
        out = subprocess.run(['ip', '-br', 'link'], capture_output=True, text=True, timeout=5).stdout
        for ln in out.splitlines():
            name = ln.split()[0].split('@')[0] if ln.split() else ''
            if name and name != 'gmtun0' and name.startswith(('tun', 'tap', 'wg')):
                return name
    except Exception:
        pass
    return None


# ---------------- управление VPN-сервисом ----------------
# Windows: sing-box.exe — консольная программа, не служба. Держим её как дочерний процесс
# (приложение запускается с правами админа через launcher.bat → UAC один раз).
_WIN = {'proc': None}


class _R:  # мимикрия под CompletedProcess (returncode/stderr) для единого кода
    def __init__(self, rc=0, err=''):
        self.returncode = rc; self.stderr = err; self.stdout = ''


def _win_singbox_alive():
    p = _WIN.get('proc')
    return p is not None and p.poll() is None


def _win_start():
    if _win_singbox_alive():
        return _R(0)
    subprocess.run(['taskkill', '/F', '/IM', 'sing-box.exe'],
                   capture_output=True, creationflags=0x08000000)   # прибить осиротевший
    try:
        _WIN['proc'] = subprocess.Popen(
            [SING_BOX, 'run', '-c', SYS_CONFIG],
            cwd=os.path.dirname(SING_BOX),          # рядом wintun.dll
            creationflags=0x08000000)               # CREATE_NO_WINDOW
    except Exception as e:
        return _R(1, str(e))
    import time
    time.sleep(0.8)
    if not _win_singbox_alive():
        return _R(1, 'sing-box завершился сразу — см. логи')
    return _R(0)


def _win_stop():
    p = _WIN.get('proc')
    if p and p.poll() is None:
        try:
            p.terminate(); p.wait(5)
        except Exception:
            try: p.kill()
            except Exception: pass
    _WIN['proc'] = None
    subprocess.run(['taskkill', '/F', '/IM', 'sing-box.exe'],
                   capture_output=True, creationflags=0x08000000)
    return _R(0)


def svc(action, unit='goodman-net.service'):
    if IS_WIN:
        if action == 'stop':
            return _win_stop()
        if action == 'restart':
            _win_stop()
        return _win_start()
    return subprocess.run(['systemctl', action, unit], capture_output=True, text=True)


def kill_unit_exists():
    if IS_WIN:
        return False
    r = subprocess.run(['systemctl', 'cat', 'goodman-net-kill.service'], capture_output=True, text=True)
    return r.returncode == 0


def killswitch(on, server_ip=''):
    """Вкл/выкл kill switch (отдельный root-юнит с nftables). (ok, details)."""
    if IS_WIN:
        return False, 'Windows: пока недоступно'
    if on:
        try:
            with open(KILL_ENV, 'w', encoding='utf-8') as f:
                f.write('SERVER_IP=%s\n' % server_ip)
        except Exception as e:
            return False, str(e)
        r = svc('restart', 'goodman-net-kill.service')
    else:
        r = svc('stop', 'goodman-net-kill.service')
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or '').strip()
    return True, ''


def svc_logs(lines=250):
    try:
        if IS_WIN:
            logf = os.path.join(os.path.dirname(SYS_CONFIG), 'singbox.log')
            if os.path.exists(logf):
                with open(logf, encoding='utf-8', errors='replace') as f:
                    return ''.join(f.readlines()[-lines:]) or '(лог пуст)'
            return '(лог службы пока пуст — подключитесь, чтобы он появился)'
        r = subprocess.run(['journalctl', '-u', 'goodman-net.service', '-n', str(lines),
                            '--no-pager', '-o', 'short'], capture_output=True, text=True, timeout=10)
        return r.stdout or r.stderr or '(журнал пуст)'
    except Exception as e:
        return 'Не удалось прочитать логи: %s' % e


def check_config():
    """sing-box check ДО запуска сервиса. '' если ок, иначе текст ошибки."""
    try:
        r = subprocess.run([SING_BOX, 'check', '-c', SYS_CONFIG],
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return (r.stderr or r.stdout or 'sing-box check failed').strip()
    except Exception as e:
        return str(e)
    return ''


def is_connected():
    if IS_WIN:
        if _win_singbox_alive():
            return True
        # процесс мог быть запущен прошлой сессией приложения — проверяем по имени
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq sing-box.exe'],
                           capture_output=True, text=True, creationflags=0x08000000)
        return 'sing-box.exe' in (r.stdout or '')
    r = subprocess.run(['systemctl', 'is-active', 'goodman-net.service'],
                       capture_output=True, text=True)
    return r.stdout.strip() == 'active'


WIN_LOG = os.path.join(os.path.dirname(SYS_CONFIG), 'singbox.log') if IS_WIN else ''


def write_sys_config(server):
    st = load_settings()
    cfg = gmcore.config_tun(server, bypass_ru=st.get('bypass_ru', True))
    if IS_WIN:
        cfg['log']['output'] = WIN_LOG   # служба Windows не отдаёт stdout → пишем лог в файл
        tun = cfg['inbounds'][0]          # iproute2_* — только Linux; на Windows убираем
        tun.pop('iproute2_table_index', None); tun.pop('iproute2_rule_index', None)
    os.makedirs(os.path.dirname(SYS_CONFIG), exist_ok=True)
    json.dump(cfg, open(SYS_CONFIG, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return cfg


def exit_geo():
    try:
        req = urllib.request.Request('https://ipwho.is/', headers={'User-Agent': 'gm'})
        d = json.load(urllib.request.urlopen(req, timeout=6))
        return {'ip': d.get('ip'), 'country_code': d.get('country_code'), 'ok': True}
    except Exception:
        for u in ('https://www.gstatic.com/generate_204', 'https://www.google.com/generate_204'):
            try:
                urllib.request.urlopen(u, timeout=5)
                return {'ip': None, 'country_code': None, 'ok': True}
            except Exception:
                pass
        return {'ok': False}


def clear_system_proxy():
    """Сбросить системный прокси, если он указывает на локальный порт (наследие Happ и т.п.).
    Наш клиент — полный туннель, прокси не нужен; чужой мёртвый прокси ломает консоль."""
    if IS_WIN:
        return
    try:
        mode = subprocess.run(['gsettings', 'get', 'org.gnome.system.proxy', 'mode'],
                              capture_output=True, text=True, timeout=5).stdout.strip().strip("'")
        if mode == 'manual':
            host = subprocess.run(['gsettings', 'get', 'org.gnome.system.proxy.http', 'host'],
                                  capture_output=True, text=True, timeout=5).stdout
            if '127.0.0.1' in host or 'localhost' in host:
                subprocess.run(['gsettings', 'set', 'org.gnome.system.proxy', 'mode', 'none'],
                               capture_output=True, timeout=5)
    except Exception:
        pass


def do_connect():
    """Подключение. Возвращает (ok, err_title, err_details)."""
    st = load_settings()
    if not st.get('servers'):
        return False, tr('err_no_sub'), ''
    # чужой VPN (Happ) не блокируем, а вычищаем: proxy тут (user), tun/маршруты/процессы —
    # в precheck.sh сервиса (ExecStartPre, от root) при старте туннеля.
    clear_system_proxy()
    cfg = write_sys_config(st['servers'][st.get('selected', 0)])
    bad = check_config()
    if bad:
        return False, tr('err_cfg'), bad
    r = svc('start')
    if r.returncode != 0:
        return False, tr('err_start'), (r.stderr or r.stdout or '').strip() + '\n\n' + svc_logs(25)
    import time
    for _ in range(6):
        time.sleep(0.7)
        if is_connected():
            if st.get('killswitch') and kill_unit_exists():
                killswitch(True, cfg['outbounds'][0].get('server', ''))
            return True, '', ''
    return False, tr('err_notup'), svc_logs(25)


def do_disconnect():
    if kill_unit_exists():
        killswitch(False)
    svc('stop')
    return True


def do_select(i):
    st = load_settings()
    st['selected'] = i
    save_settings(st)
    if is_connected():
        cfg = write_sys_config(st['servers'][i])
        svc('restart')
        if st.get('killswitch') and kill_unit_exists():
            killswitch(True, cfg['outbounds'][0].get('server', ''))


def background_refresh():
    """Каждые 30 мин обновляет подписку (устройство активно + свежие ключи + мета ЛК)."""
    import time
    first = True
    while True:
        time.sleep(3 if first else 1800)   # первая итерация сразу — подтянуть мету ЛК
        first = False
        st = load_settings()
        if st.get('sub'):
            try:
                servers, e, meta = sub_fetch(st['sub'])
                if servers:
                    old = json.dumps(st.get('servers', []), sort_keys=True)
                    st = apply_sub(st['sub'], servers, meta, st)
                    if is_connected() and json.dumps(servers, sort_keys=True) != old:
                        write_sys_config(servers[st['selected']])
                        svc('restart')
            except Exception:
                pass


# ---------------- нативное GTK-приложение ----------------
CSS_DARK = b"""
/* mobile-app theme: dark bg #1C1B1F, orange accent #f97910 */
window { background: #1C1B1F; }
.title { color: #E6E1E5; font-size: 19px; font-weight: 800; }
.status-on { color: #22c55e; font-size: 16px; font-weight: 700; }
.status-off { color: #9C9C9C; font-size: 16px; font-weight: 700; }
.status-busy { color: #E6E1E5; font-size: 16px; font-weight: 700; }
.hint { color: #9C9C9C; font-size: 13px; }
.power { border-radius: 999px; min-width: 168px; min-height: 168px;
  background-image: none; background-color: #646464;
  color: #ffffff; border: none; box-shadow: 0 10px 30px rgba(0,0,0,.5); font-size: 46px;
  outline: none; }
.power:focus { outline: none; }
.power:hover { background-color: #6f6f6f; }
.power-on { background-color: #16a34a; color: #ffffff; }
.power-on:hover { background-color: #18b452; }
.top { color: #f97910; background: rgba(249,121,16,.10); border: 1px solid rgba(249,121,16,.35);
  border-radius: 10px; padding: 7px 14px; font-size: 13px; font-weight: 600; outline: none; }
.top:hover { background: rgba(249,121,16,.18); }
.qa { color: #f97910; background: transparent; border: none; font-size: 13px; font-weight: 600;
  padding: 6px 10px; outline: none; }
.qa:hover { background: rgba(249,121,16,.12); border-radius: 8px; }
.qa-on { color: #ffffff; background: rgba(249,121,16,.22); border-radius: 8px; }
.side { border-radius: 999px; min-width: 50px; min-height: 50px; font-size: 18px;
  background: rgba(255,255,255,.06); color: #d6d2d6; border: 1px solid rgba(255,255,255,.12);
  outline: none; }
.side:hover { background: rgba(255,255,255,.12); }
.card { background: #2A2A2E; border-radius: 14px; }
.subinfo { background: rgba(124,58,237,.10); border: 1px solid rgba(124,58,237,.40); border-radius: 14px; }
.srv-row { color: #E6E1E5; font-size: 14px; padding: 4px; }
list { background: transparent; }
row { border-radius: 10px; }
row:selected { background: rgba(249,121,16,.20); }
entry { background: #2A2A2E; color: #E6E1E5; border: 1px solid #474747; border-radius: 10px; padding: 10px; caret-color: #f97910; }
.act { background: #f97910; color: #ffffff; border-radius: 10px; font-weight: 700; padding: 10px; border: none; }
.act:hover { background: #ff8a24; }
.errbox { background: rgba(239,68,68,.10); border: 1px solid rgba(239,68,68,.45); border-radius: 12px; }
.errtitle { color: #fda4a4; font-weight: 700; font-size: 13px; }
.errtext { color: #fecaca; font-size: 11px; }
textview, textview text { background: #141416; color: #d6d2d6; }
.mini { background: rgba(255,255,255,.07); color: #ece8ec; border: 1px solid rgba(255,255,255,.15); border-radius: 8px; font-size: 12px; padding: 6px; }
"""

CSS_LIGHT = b"""
/* mobile day theme: white bg, purple accent #7C3AED */
window { background: #FFFFFF; }
.title { color: #1C1B1F; font-size: 19px; font-weight: 800; }
.status-on { color: #16a34a; font-size: 16px; font-weight: 700; }
.status-off { color: #9C9C9C; font-size: 16px; font-weight: 700; }
.status-busy { color: #1C1B1F; font-size: 16px; font-weight: 700; }
.hint { color: #8a8a8a; font-size: 13px; }
.power { border-radius: 999px; min-width: 168px; min-height: 168px;
  background-image: none; background-color: #9C9C9C;
  color: #ffffff; border: none; box-shadow: 0 10px 26px rgba(0,0,0,.18); font-size: 46px;
  outline: none; }
.power:focus { outline: none; }
.power:hover { background-color: #adadad; }
.power-on { background-color: #16a34a; color: #ffffff; }
.power-on:hover { background-color: #18b452; }
.top { color: #7C3AED; background: rgba(124,58,237,.08); border: 1px solid rgba(124,58,237,.30);
  border-radius: 10px; padding: 7px 14px; font-size: 13px; font-weight: 600; outline: none; }
.top:hover { background: rgba(124,58,237,.16); }
.qa { color: #7C3AED; background: transparent; border: none; font-size: 13px; font-weight: 600;
  padding: 6px 10px; outline: none; }
.qa:hover { background: rgba(124,58,237,.10); border-radius: 8px; }
.qa-on { color: #ffffff; background: rgba(124,58,237,.85); border-radius: 8px; }
.side { border-radius: 999px; min-width: 50px; min-height: 50px; font-size: 18px;
  background: #f1f1f4; color: #34343a; border: 1px solid #dcdce2; outline: none; }
.side:hover { background: #e6e6ec; }
.card { background: #f6f6f8; border-radius: 14px; border: 1px solid #e2e2e8; }
.subinfo { background: rgba(124,58,237,.08); border: 1px solid rgba(124,58,237,.35); border-radius: 14px; }
.srv-row { color: #1C1B1F; font-size: 14px; padding: 4px; }
list { background: transparent; }
row { border-radius: 10px; }
row:selected { background: rgba(124,58,237,.14); }
entry { background: #ffffff; color: #1C1B1F; border: 1px solid #cfcfd6; border-radius: 10px; padding: 10px; }
.act { background: #7C3AED; color: #ffffff; border-radius: 10px; font-weight: 700; padding: 10px; border: none; }
.act:hover { background: #8b4bf5; }
.errbox { background: rgba(239,68,68,.07); border: 1px solid rgba(239,68,68,.4); border-radius: 12px; }
.errtitle { color: #b91c1c; font-weight: 700; font-size: 13px; }
.errtext { color: #991b1b; font-size: 11px; }
textview, textview text { background: #ffffff; color: #2a2a30; }
.mini { background: #f1f1f4; color: #34343a; border: 1px solid #dcdce2; border-radius: 8px; font-size: 12px; padding: 6px; }
"""


def run_gtk():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib, Gdk, GdkPixbuf, Pango

    css_provider = Gtk.CssProvider()

    def apply_theme():
        theme = load_settings().get('theme', 'dark')
        css_provider.load_from_data(CSS_LIGHT if theme == 'light' else CSS_DARK)

    class Win(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title='GoodMan Net')
            self.set_default_size(430, 720)
            self.set_position(Gtk.WindowPosition.CENTER)
            try:
                self.set_icon(GdkPixbuf.Pixbuf.new_from_file(os.path.join(RES_DIR, 'logo.png')))
            except Exception:
                pass
            self.busy = False
            self.connected = False
            self.logwin = None
            self._speed_running = False

            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            apply_theme()

            hb = Gtk.HeaderBar(title='GoodMan Net')
            hb.set_show_close_button(True)
            self.set_titlebar(hb)

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5,
                           margin_top=16, margin_bottom=12, margin_start=22, margin_end=22)
            self.add(root)

            # верхний ряд: Личный кабинет · Telegram (одинаковой ширины, как в мобилке)
            toprow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            toprow.set_halign(Gtk.Align.CENTER); toprow.set_margin_top(8)
            toprow.set_homogeneous(True)      # обе кнопки одинаковой ширины
            self.lktop = Gtk.Button(label='👤 Личный кабинет'); self.lktop.set_can_focus(False)
            self.lktop.get_style_context().add_class('top'); self.lktop.set_size_request(165, -1)
            self.lktop.connect('clicked', lambda *_: self.open_lk())
            tgtop = Gtk.Button(label='✈ Telegram'); tgtop.set_can_focus(False)
            tgtop.get_style_context().add_class('top'); tgtop.set_size_request(165, -1)
            tgtop.connect('clicked', lambda *_: self.open_url('https://t.me/goodmanNet_bot'))
            toprow.pack_start(self.lktop, True, True, 0)
            toprow.pack_start(tgtop, True, True, 0)
            root.pack_start(toprow, False, False, 0)

            # ⚙  [POWER]  📋 — меню и логи по бокам от кнопки включения
            prow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
            prow.set_halign(Gtk.Align.CENTER)
            prow.set_margin_top(10); prow.set_margin_bottom(6)

            self.menubtn = Gtk.MenuButton(label='⚙')
            self.menubtn.set_can_focus(False)
            self.menubtn.get_style_context().add_class('side')
            self.menubtn.set_valign(Gtk.Align.CENTER)
            self.menu = Gtk.Menu()
            self.menubtn.set_popup(self.menu)
            prow.pack_start(self.menubtn, False, False, 0)

            self.power = Gtk.Button(label='⏻')
            self.power.set_can_focus(False)
            self.power.get_style_context().add_class('power')
            self.power.set_valign(Gtk.Align.CENTER)
            self.power.connect('clicked', lambda *_: self.toggle())
            self.power.set_always_show_image(True)
            try:                              # логотип-щит для состояния «подключено»
                self._logo_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    os.path.join(RES_DIR, 'logo.png'), 104, 104, True)
            except Exception:
                self._logo_pb = None
            prow.pack_start(self.power, False, False, 0)

            self.logbtn = Gtk.Button(label='📋')
            self.logbtn.set_can_focus(False)
            self.logbtn.get_style_context().add_class('side')
            self.logbtn.set_valign(Gtk.Align.CENTER)
            self.logbtn.connect('clicked', lambda *_: self.show_logs())
            prow.pack_start(self.logbtn, False, False, 0)

            root.pack_start(prow, False, False, 0)

            self.status = Gtk.Label(label=''); self.status.get_style_context().add_class('status-off')
            root.pack_start(self.status, False, False, 0)

            # строка результата замера скорости (между статусом и рядом действий)
            self.speedlbl = Gtk.Label(label=''); self.speedlbl.get_style_context().add_class('hint')
            self.speedlbl.set_no_show_all(True)
            root.pack_start(self.speedlbl, False, False, 0)

            # ряд быстрых действий под статусом (как в мобилке): Обновить · Мимо VPN · Kill switch
            self.qarow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            self.qarow.set_halign(Gtk.Align.CENTER); self.qarow.set_margin_top(6); self.qarow.set_margin_bottom(2)
            self.refbtn = Gtk.Button(label='🔄 Обновить'); self.refbtn.set_can_focus(False)
            self.refbtn.get_style_context().add_class('qa')
            self.refbtn.connect('clicked', lambda *_: self.refresh_sub())
            self.bypbtn = Gtk.Button(label='📱 Мимо VPN'); self.bypbtn.set_can_focus(False)
            self.bypbtn.get_style_context().add_class('qa')
            self.bypbtn.connect('clicked', lambda *_: self.qa_bypass())
            self.spdbtn = Gtk.Button(label='📊 Скорость'); self.spdbtn.set_can_focus(False)
            self.spdbtn.get_style_context().add_class('qa')
            self.spdbtn.connect('clicked', lambda *_: self.qa_speed())
            self.killbtn = Gtk.Button(label='🛡 Kill switch'); self.killbtn.set_can_focus(False)
            self.killbtn.get_style_context().add_class('qa')
            self.killbtn.connect('clicked', lambda *_: self.qa_kill())
            for b in (self.refbtn, self.bypbtn, self.spdbtn, self.killbtn):
                self.qarow.pack_start(b, False, False, 0)
            root.pack_start(self.qarow, False, False, 0)
            self.hint = Gtk.Label(label=''); self.hint.get_style_context().add_class('hint')
            root.pack_start(self.hint, False, False, 0)
            # аккуратная фиолетовая карточка с ЛК + статусом подписки (как bg_subinfo в мобилке)
            self.subcard = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.subcard.get_style_context().add_class('subinfo')
            self.subcard.set_margin_top(8)
            for m in ('set_margin_start', 'set_margin_end'):
                getattr(self.subcard, m)(4)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                            margin_top=12, margin_bottom=12, margin_start=14, margin_end=14)
            # одна метка на весь текст — равномерные отступы между всеми строками
            self.subtext = Gtk.Label(label='', selectable=True, xalign=0.5)
            self.subtext.get_style_context().add_class('hint')
            self.subtext.set_line_wrap(True); self.subtext.set_justify(Gtk.Justification.CENTER)
            self.subtext.set_max_width_chars(44)
            inner.pack_start(self.subtext, False, False, 0)
            self.subcard.pack_start(inner, False, False, 0)
            root.pack_start(self.subcard, False, False, 0)

            # панель ошибки (копируемая)
            self.errbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.errbox.get_style_context().add_class('errbox')
            self.errbox.set_margin_top(4)
            eh = Gtk.Box(spacing=6, margin_top=8, margin_start=10, margin_end=10)
            self.errtitle = Gtk.Label(label='', xalign=0); self.errtitle.get_style_context().add_class('errtitle')
            self.errtitle.set_line_wrap(True)
            eh.pack_start(self.errtitle, True, True, 0)
            ex = Gtk.Button(label='✕'); ex.get_style_context().add_class('mini')
            ex.connect('clicked', lambda *_: self.errbox.hide())
            eh.pack_end(ex, False, False, 0)
            self.errbox.pack_start(eh, False, False, 0)
            sw = Gtk.ScrolledWindow(); sw.set_min_content_height(90); sw.set_max_content_height(150)
            sw.set_margin_start(10); sw.set_margin_end(10)
            self.errview = Gtk.TextView(editable=False, cursor_visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            self.errview.get_style_context().add_class('errtext')
            try:
                self.errview.modify_font(Pango.FontDescription('Monospace 8'))
            except Exception:
                pass
            sw.add(self.errview)
            self.errbox.pack_start(sw, True, True, 0)
            self.ecopy = Gtk.Button(label=''); self.ecopy.get_style_context().add_class('mini')
            self.ecopy.set_margin_start(10); self.ecopy.set_margin_end(10); self.ecopy.set_margin_bottom(8)
            self.ecopy.connect('clicked', lambda *_: self.copy_err())
            self.errbox.pack_start(self.ecopy, False, False, 0)
            root.pack_start(self.errbox, False, False, 0)

            # ввод подписки
            self.setup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.suburl = Gtk.Entry()
            self.setup.pack_start(self.suburl, False, False, 0)
            self.addbtn = Gtk.Button(label=''); self.addbtn.get_style_context().add_class('act')
            self.addbtn.connect('clicked', lambda *_: self.save_sub())
            self.setup.pack_start(self.addbtn, False, False, 0)
            root.pack_start(self.setup, False, False, 0)

            # список серверов
            frame = Gtk.Frame(); frame.get_style_context().add_class('card'); frame.set_shadow_type(Gtk.ShadowType.NONE)
            swl = Gtk.ScrolledWindow(); swl.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            swl.set_min_content_height(170)
            self.srvlist = Gtk.ListBox(); self.srvlist.set_selection_mode(Gtk.SelectionMode.SINGLE)
            self.srvlist.connect('row-activated', self.on_row)
            swl.add(self.srvlist); frame.add(swl)
            root.pack_start(frame, True, True, 0)

            self.build_menu()
            self.update_texts()
            self.refresh_servers()
            self.refresh_state()
            GLib.timeout_add_seconds(4, self._tick)
            self.show_all()
            self.errbox.hide()
            self._sync_setup_visibility()

        # ---------- меню ----------
        def build_menu(self):
            for ch in self.menu.get_children():
                self.menu.remove(ch)
            st = load_settings()
            items = [
                ('menu_refresh', lambda *_: self.refresh_sub(), None),
                ('menu_change', lambda *_: self.toggle_setup(), None),
                ('menu_logout', lambda *_: self.logout_sub(), None),
                (None, None, None),
                ('menu_kill', self.on_kill_toggle, bool(st.get('killswitch'))),
                ('menu_bypass', self.on_bypass_toggle, st.get('bypass_ru', True)),
                (None, None, None),
                ('menu_theme', self.on_theme_toggle, st.get('theme', 'dark') == 'light'),
                ('menu_lang', self.on_lang_toggle, None),
                (None, None, None),
                ('menu_logs', lambda *_: self.show_logs(), None),
            ]
            for key, cb, checked in items:
                if key is None:
                    self.menu.append(Gtk.SeparatorMenuItem())
                    continue
                if checked is None:
                    mi = Gtk.MenuItem(label=tr(key))
                    mi.connect('activate', cb)
                else:
                    mi = Gtk.CheckMenuItem(label=tr(key))
                    mi.set_active(checked)
                    mi.connect('toggled', cb)
                self.menu.append(mi)
            self.menu.show_all()

        def on_kill_toggle(self, mi):
            st = load_settings()
            want = mi.get_active()
            if want and not kill_unit_exists():
                mi.set_active(False)
                self.show_err(tr('err_kill'), tr('err_kill_d'))
                return
            st['killswitch'] = want
            save_settings(st)
            if is_connected():
                if want:
                    ip = ''
                    try:
                        ip = json.load(open(SYS_CONFIG))['outbounds'][0].get('server', '')
                    except Exception:
                        pass
                    ok, d = killswitch(True, ip)
                    if not ok:
                        self.show_err(tr('err_kill'), d)
                else:
                    killswitch(False)

        def on_bypass_toggle(self, mi):
            st = load_settings()
            st['bypass_ru'] = mi.get_active()
            save_settings(st)
            if is_connected():
                write_sys_config(st['servers'][st.get('selected', 0)])
                svc('restart')

        def on_theme_toggle(self, mi):
            st = load_settings()
            st['theme'] = 'light' if mi.get_active() else 'dark'
            save_settings(st)
            apply_theme()

        def on_lang_toggle(self, mi):
            st = load_settings()
            st['lang'] = 'en' if st.get('lang', 'ru') == 'ru' else 'ru'
            save_settings(st)
            self.build_menu()
            self.update_texts()
            self.refresh_state()

        # ---------- helpers ----------
        def update_texts(self):
            self.menubtn.set_tooltip_text(tr('tt_menu'))
            self.logbtn.set_tooltip_text(tr('tt_logs'))
            self.power.set_tooltip_text(tr('tt_power'))
            self.suburl.set_placeholder_text(tr('sub_placeholder'))
            self.addbtn.set_label(tr('sub_add'))
            self.refbtn.set_label(tr('qa_refresh'))
            self.bypbtn.set_label(tr('qa_bypass'))
            self.spdbtn.set_label(tr('qa_speed'))
            self.killbtn.set_label(tr('qa_kill'))
            self.lktop.set_label('👤 ' + tr('lk'))
            self.ecopy.set_label(tr('copy_error'))
            self._sync_setup_visibility()

        def _sync_setup_visibility(self):
            st = load_settings()
            has = bool(st.get('servers'))
            if not getattr(self, '_setup_forced', False):
                self.setup.set_visible(not has)
            self.qarow.set_visible(has)
            # подсветка активных тумблеров (Мимо VPN / Kill switch)
            for btn, on in ((self.bypbtn, st.get('bypass_ru', True)),
                            (self.killbtn, st.get('killswitch', False))):
                sc = btn.get_style_context()
                (sc.add_class if on else sc.remove_class)('qa-on')
            self.lktop.set_visible(bool(st.get('lk')))
            self.hint.set_label('' if has else tr('add_sub_hint'))
            acc = st.get('account', '')
            # всё в одну метку (равномерные отступы): ЛК + статус подписки, каждая мысль с новой строки
            lines = []
            if acc:
                lines.append('%s: %s' % (tr('lk'), acc))
            lines += [cap_first(p) for p in (st.get('announce', '') or '').split(' · ')
                      if p.strip() and 'happ' not in p.lower()]
            # остаток трафика для сервера Plus (метрируется только он)
            servers = st.get('servers', []); sel = st.get('selected', 0)
            name = servers[sel]['name'] if 0 <= sel < len(servers) else ''
            tinfo = st.get('traffic') or {}
            if 'plus' in name.lower() and tinfo.get('total'):
                used = tinfo.get('up', 0) + tinfo.get('down', 0)
                left = max(0, tinfo['total'] - used)
                lines.append('Осталось трафика: %s из %s' % (fmt_bytes(left), fmt_bytes(tinfo['total'])))
            self.subtext.set_label('\n'.join(lines))
            self.subcard.set_visible(bool(lines))

        def open_url(self, url):
            try:
                Gtk.show_uri_on_window(self, url, Gdk.CURRENT_TIME)
            except Exception:
                import webbrowser
                webbrowser.open(url)

        def open_lk(self):
            self.open_url(load_settings().get('lk') or 'https://gdman.ink')

        def qa_bypass(self):
            st = load_settings()
            st['bypass_ru'] = not st.get('bypass_ru', True)
            save_settings(st)
            self._sync_setup_visibility()
            if is_connected():
                self.set_status(tr('switching'), 'status-busy')
                def work():
                    write_sys_config(st['servers'][st.get('selected', 0)]); svc('restart')
                    GLib.idle_add(self.refresh_state)
                threading.Thread(target=work, daemon=True).start()

        def qa_kill(self):
            st = load_settings()
            want = not st.get('killswitch', False)
            if want and not kill_unit_exists():
                self.show_err(tr('err_kill'), tr('err_kill_d')); return
            st['killswitch'] = want
            save_settings(st)
            self._sync_setup_visibility()
            if is_connected():
                if want:
                    ip = ''
                    try:
                        ip = json.load(open(SYS_CONFIG))['outbounds'][0].get('server', '')
                    except Exception:
                        pass
                    ok, d = killswitch(True, ip)
                    if not ok:
                        self.show_err(tr('err_kill'), d)
                else:
                    killswitch(False)

        def _set_speed(self, text):
            self.speedlbl.set_label(text or '')
            self.speedlbl.set_visible(bool(text))

        def qa_speed(self):
            if self._speed_running:
                return
            if not is_connected():
                self._set_speed('📊 ' + tr('speed_off')); return
            self._speed_running = True
            self._set_speed('📊 ' + tr('speed_run'))
            def work():
                import time as _t
                mbps = None; err = ''
                for url in ('https://speed.cloudflare.com/__down?bytes=20000000',
                            'https://speedtest.selectel.ru/100MB',
                            'http://cachefly.cachefly.net/10mb.test'):
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 gm'})
                        t0 = _t.time(); total = 0
                        with urllib.request.urlopen(req, timeout=20) as r:
                            while _t.time() - t0 < 10:
                                chunk = r.read(65536)
                                if not chunk:
                                    break
                                total += len(chunk)
                        dt = max(0.15, _t.time() - t0)
                        if total > 500000:            # хотя бы 0.5 МБ скачали — замер валиден
                            mbps = (total * 8) / dt / 1e6
                            break
                    except Exception as e:
                        err = str(e); continue
                def done():
                    self._speed_running = False
                    self._set_speed('📊 %.1f Мбит/с' % mbps if mbps else '📊 —')
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        def toggle_setup(self):
            self._setup_forced = not self.setup.get_visible()
            self.setup.set_visible(self._setup_forced or not load_settings().get('servers'))
            if self.setup.get_visible():
                st = load_settings()
                if st.get('sub'):
                    self.suburl.set_text(st['sub'])
                self.suburl.grab_focus()

        def show_err(self, title, details):
            self.errtitle.set_label(title or tr('error'))
            self.errview.get_buffer().set_text(details or '')
            self.errbox.show_all()

        def copy_err(self):
            buf = self.errview.get_buffer()
            txt = self.errtitle.get_label() + '\n' + buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(txt, -1)

        def set_status(self, txt, cls):
            for c in ('status-on', 'status-off', 'status-busy'):
                self.status.get_style_context().remove_class(c)
            self.status.get_style_context().add_class(cls)
            self.status.set_label(txt)

        def set_power(self, on):
            sc = self.power.get_style_context()
            (sc.add_class if on else sc.remove_class)('power-on')
            if on and self._logo_pb is not None:
                self.power.set_label('')
                self.power.set_image(Gtk.Image.new_from_pixbuf(self._logo_pb))
            else:
                self.power.set_image(None)
                self.power.set_label('⏻')

        # ---------- список серверов ----------
        def refresh_servers(self):
            for ch in self.srvlist.get_children():
                self.srvlist.remove(ch)
            st = load_settings()
            for i, s in enumerate(st.get('servers', [])):
                row = Gtk.ListBoxRow()
                lb = Gtk.Label(label=s['name'], xalign=0)
                lb.get_style_context().add_class('srv-row')
                lb.set_margin_top(4); lb.set_margin_bottom(4); lb.set_margin_start(12)
                row.add(lb)
                self.srvlist.add(row)
                if i == st.get('selected', 0):
                    self.srvlist.select_row(row)
            self.srvlist.show_all()

        def on_row(self, box, row):
            i = row.get_index()
            self.set_status(tr('switching'), 'status-busy')
            threading.Thread(target=lambda: (do_select(i), GLib.idle_add(self.refresh_state)), daemon=True).start()

        # ---------- подписка ----------
        def refresh_sub(self):
            st = load_settings()
            if not st.get('sub'):
                self.toggle_setup(); return
            self.errbox.hide()
            self.set_status(tr('sub_updating'), 'status-busy')
            url = st['sub']
            def work():
                try:
                    servers, e, meta = sub_fetch(url)
                except Exception as ex:
                    GLib.idle_add(lambda: (self.show_err(tr('err_sub_upd'), str(ex)),
                                           self.refresh_state()))
                    return
                def done():
                    if e:
                        self.show_err(e, '')
                    elif servers:
                        apply_sub(url, servers, meta)
                        self.refresh_servers()
                        self._sync_setup_visibility()
                    self.refresh_state()
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        def logout_sub(self):
            dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                    message_type=Gtk.MessageType.QUESTION,
                                    buttons=Gtk.ButtonsType.YES_NO,
                                    text=tr('logout_q'))
            dlg.format_secondary_text(tr('logout_msg'))
            ans = dlg.run(); dlg.destroy()
            if ans != Gtk.ResponseType.YES:
                return
            def work():
                if is_connected():
                    do_disconnect()
                st = load_settings()
                for k in ('sub', 'servers', 'selected', 'lk', 'account', 'announce'):
                    st.pop(k, None)
                st['servers'] = []; st['selected'] = 0
                save_settings(st)
                def done():
                    self._setup_forced = False
                    self.suburl.set_text('')
                    self.refresh_servers()
                    self._sync_setup_visibility()
                    self.refresh_state()
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        def save_sub(self):
            url = self.suburl.get_text().strip()
            if not url:
                return
            self.errbox.hide()
            self.set_status(tr('sub_loading'), 'status-busy')
            def work():
                try:
                    servers, e, meta = sub_fetch(url)
                except Exception as ex:
                    GLib.idle_add(lambda: (self.show_err(tr('err_sub_load'), str(ex)),
                                           self.refresh_state()))
                    return
                def done():
                    if e:
                        self.show_err(e, '')
                    elif not servers:
                        self.show_err(tr('err_sub_empty'), '')
                    else:
                        st = load_settings()
                        st['selected'] = 0
                        apply_sub(url, servers, meta, st)
                        self._setup_forced = False
                        self.refresh_servers()
                        self._sync_setup_visibility()
                    self.refresh_state()
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        # ---------- подключение ----------
        def toggle(self):
            if self.busy:
                return
            st = load_settings()
            if not st.get('servers'):
                self.suburl.grab_focus(); return
            self.busy = True
            self.errbox.hide()
            self.set_status(tr('disconnecting') if self.connected else tr('connecting'), 'status-busy')
            def work():
                if self.connected:
                    do_disconnect(); ok, t, d = True, '', ''
                else:
                    ok, t, d = do_connect()
                def done():
                    self.busy = False
                    if not ok:
                        self.show_err(t, d)
                    self.refresh_state()
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        # ---------- статус ----------
        def refresh_state(self):
            was = getattr(self, 'connected', False)
            self.connected = is_connected()
            self.set_power(self.connected)
            if self.busy:
                self._sync_setup_visibility()
                return
            if self.connected:
                # показываем кэш гео (стабильно, без мерцания); текст меняем только если реально изменился
                cached = getattr(self, '_geo_txt', '')
                self.set_status(cached or ('✅ ' + tr('connected')), 'status-on')
                # гео запрашиваем редко: при первом подключении и раз в ~30с (каждый 8-й тик)
                self._geo_n = getattr(self, '_geo_n', 0) + 1
                if not was or not cached or self._geo_n % 8 == 0:
                    def geo():
                        g = exit_geo()
                        if g.get('ok'):
                            flag = FLAGS.get((g.get('country_code') or '').upper(), '🌍')
                            ip = g.get('ip') or ''
                            txt = ('%s %s · %s' % (flag, tr('connected'), ip)).strip(' ·')
                            self._geo_txt = txt
                            GLib.idle_add(lambda: (not self.busy and self.connected and
                                          self.status.get_label() != txt) and
                                          self.set_status(txt, 'status-on'))
                    threading.Thread(target=geo, daemon=True).start()
            else:
                self._geo_txt = ''
                if not self._speed_running:
                    self._set_speed('')
                self.set_status(tr('disconnected'), 'status-off')
            self._sync_setup_visibility()

        def _tick(self):
            if not self.busy:
                threading.Thread(target=lambda: GLib.idle_add(self.refresh_state), daemon=True).start()
            return True

        # ---------- логи ----------
        def show_logs(self):
            if self.logwin:
                self.logwin.present(); self._load_logs(); return
            w = Gtk.Window(title=tr('logs_title'))
            w.set_default_size(680, 520); w.set_transient_for(self)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
            sw = Gtk.ScrolledWindow()
            self.logview = Gtk.TextView(editable=False, cursor_visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            try:
                self.logview.modify_font(Pango.FontDescription('Monospace 9'))
            except Exception:
                pass
            sw.add(self.logview)
            box.pack_start(sw, True, True, 0)
            hbx = Gtk.Box(spacing=8)
            b1 = Gtk.Button(label=tr('logs_refresh')); b1.get_style_context().add_class('mini')
            b1.connect('clicked', lambda *_: self._load_logs())
            b2 = Gtk.Button(label=tr('logs_copy')); b2.get_style_context().add_class('mini')
            def cpy(*_):
                buf = self.logview.get_buffer()
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(
                    buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), -1)
            b2.connect('clicked', cpy)
            hbx.pack_start(b1, True, True, 0); hbx.pack_start(b2, True, True, 0)
            box.pack_start(hbx, False, False, 0)
            w.add(box)
            def closed(*_):
                self.logwin = None
            w.connect('destroy', closed)
            w.show_all()
            self.logwin = w
            self._load_logs()

        def _load_logs(self):
            self.logview.get_buffer().set_text(tr('loading'))
            def work():
                logs = svc_logs()
                GLib.idle_add(lambda: self.logview.get_buffer().set_text(logs))
            threading.Thread(target=work, daemon=True).start()

    class App(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='ink.gdman.goodmannet')
            self.win = None

        def do_activate(self):
            if not self.win:
                self.win = Win(self)
            self.win.present()

    threading.Thread(target=background_refresh, daemon=True).start()
    App().run([])


# ---------------- web-UI fallback (Windows / нет GTK) ----------------
def run_web():
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    PORT = 8765

    def jerr(msg, details=''):
        return json.dumps({'error': msg, 'details': details}, ensure_ascii=False)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype='application/json'):
            b = body.encode('utf-8') if isinstance(body, str) else body
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                return self._send(200, open(os.path.join(RES_DIR, 'ui.html'), encoding='utf-8').read(),
                                  'text/html; charset=utf-8')
            if self.path == '/logo.png':
                try:
                    return self._send(200, open(os.path.join(RES_DIR, 'logo.png'), 'rb').read(), 'image/png')
                except Exception:
                    return self._send(404, b'', 'image/png')
            if self.path == '/api/state':
                st = load_settings()
                conn = is_connected()
                out = {'connected': conn, 'sub_set': bool(st.get('servers')),
                       'servers': [s['name'] for s in st.get('servers', [])],
                       'selected': st.get('selected', 0),
                       'account': st.get('account', ''), 'lk': st.get('lk', '')}
                if conn:
                    g = exit_geo()
                    out['exit_ok'] = g.get('ok'); out['exit_ip'] = g.get('ip')
                    out['flag'] = FLAGS.get((g.get('country_code') or '').upper(), '🌍')
                return self._send(200, json.dumps(out, ensure_ascii=False))
            if self.path == '/api/logs':
                return self._send(200, json.dumps({'logs': svc_logs()}, ensure_ascii=False))
            return self._send(404, '{}')

        def do_POST(self):
            ln = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(ln) or '{}')
            st = load_settings()
            try:
                if self.path == '/api/sub':
                    try:
                        servers, e, meta = sub_fetch(data['url'])
                    except Exception as ex:
                        return self._send(200, jerr('Не удалось загрузить подписку', str(ex)))
                    if e:
                        return self._send(200, jerr(e))
                    if not servers:
                        return self._send(200, jerr('Подписка пуста или неверная ссылка'))
                    st['selected'] = 0
                    apply_sub(data['url'], servers, meta, st)
                    return self._send(200, json.dumps({'ok': True, 'servers': [s['name'] for s in servers]},
                                                      ensure_ascii=False))
                if self.path == '/api/select':
                    do_select(int(data['index']))
                    return self._send(200, '{"ok":true}')
                if self.path == '/api/connect':
                    ok, t, d = do_connect()
                    return self._send(200, '{"ok":true}' if ok else jerr(t, d))
                if self.path == '/api/disconnect':
                    do_disconnect()
                    return self._send(200, '{"ok":true}')
            except Exception as e:
                return self._send(200, jerr('Внутренняя ошибка приложения', repr(e)))
            return self._send(404, '{}')

    def open_window():
        # Windows: окно приложения через Edge --app (без вкладок, как нативное). Есть на любой Win10/11.
        if IS_WIN:
            for e in (os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
                      os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe')):
                if os.path.exists(e):
                    try:
                        subprocess.Popen([e, '--app=' + url, '--window-size=440,800'])
                        return
                    except Exception:
                        break
            try:
                subprocess.Popen('cmd /c start msedge --app=' + url, shell=True)
                return
            except Exception:
                pass
        webbrowser.open(url)

    url = 'http://127.0.0.1:%d/' % PORT
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    except OSError:
        open_window()   # уже запущено — просто открыть окно
        return
    threading.Thread(target=background_refresh, daemon=True).start()
    if '--no-browser' not in sys.argv:
        threading.Timer(0.6, open_window).start()
    print('GoodMan Net запущен:', url)
    srv.serve_forever()


def ensure_win_shortcut():
    """Создать ярлык GoodMan Net на рабочем столе (один раз), если запущен как .exe."""
    if not (IS_WIN and getattr(sys, 'frozen', False)):
        return
    try:
        exe = sys.executable
        ps = ("$d=[Environment]::GetFolderPath('Desktop');"
              "$l=Join-Path $d 'GoodMan Net.lnk';"
              "if(-not (Test-Path $l)){"
              "$w=New-Object -ComObject WScript.Shell;$s=$w.CreateShortcut($l);"
              "$s.TargetPath='%s';$s.IconLocation='%s,0';$s.Description='GoodMan Net VPN';$s.Save()}"
              % (exe, exe))
        subprocess.run(['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps],
                       capture_output=True, timeout=12, creationflags=0x08000000)
    except Exception:
        pass


# ---------------- нативный tkinter-интерфейс (Windows / fallback) ----------------
def _clean_name(n):
    # убрать флаг-эмодзи и прочие ведущие эмодзи (на Windows рисуются буквами/квадратами)
    import re
    return re.sub(r'^[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍ ]+', '', n).strip() or n


def _code_from_name(n):
    # ведущие региональные индикаторы (флаг-эмодзи) -> ISO-код страны (напр. 🇬🇧 -> 'gb')
    cs = []
    for ch in n:
        o = ord(ch)
        if 0x1F1E6 <= o <= 0x1F1FF:
            cs.append(chr(o - 0x1F1E6 + ord('a')))
        elif cs:
            break
    return ''.join(cs) if len(cs) == 2 else ''


def run_tk():
    import tkinter as tk
    from tkinter import font as tkfont

    BG = '#12131A'; CARD = '#1B1D27'; FG = '#E6E1E5'; MUT = '#8A90A0'
    GREEN = '#22c55e'; GRAY = '#4a4d5a'; ACC = '#5B8DEF'; RED = '#ef4444'
    CARD2 = '#232635'

    root = tk.Tk()
    root.title('GoodMan Net')
    root.configure(bg=BG)
    root.geometry('440x800')
    root.minsize(410, 700)
    try:
        root.iconphoto(True, tk.PhotoImage(file=os.path.join(RES_DIR, 'logo.png')))
    except Exception:
        pass
    F = 'Segoe UI'

    st_data = {'busy': False, 'connected': False, 'speed_running': False, 'geo': '',
               'logwin': None, 'logo': None, 'logo_id': None}

    def ui(fn):
        try: root.after(0, fn)
        except Exception: pass

    # ----- флаги стран (PNG) — на Windows эмодзи-флаги не рисуются -----
    FLAGIMG = {}
    _flagdir = os.path.join(RES_DIR, 'flags')
    def flag_for(code):
        code = (code or '').lower()
        if not code:
            return None
        if code not in FLAGIMG:
            try:
                FLAGIMG[code] = tk.PhotoImage(file=os.path.join(_flagdir, code + '.png'))
            except Exception:
                FLAGIMG[code] = None
        return FLAGIMG[code]

    # ----- верхний ряд: ЛК + Telegram (равной ширины, как в Linux) -----
    def open_url(u):
        import webbrowser
        try: webbrowser.open(u)
        except Exception: pass

    top = tk.Frame(root, bg=BG); top.pack(pady=(18, 6))
    def mk_top(txt, cmd):
        b = tk.Label(top, text=txt, bg=CARD2, fg=ACC, font=(F, 10, 'bold'),
                     padx=14, pady=8, cursor='hand2')
        b.bind('<Button-1>', lambda e: cmd())
        b.bind('<Enter>', lambda e: b.config(bg='#2c3145'))
        b.bind('<Leave>', lambda e: b.config(bg=CARD2))
        return b
    lk_btn = mk_top('👤  Личный кабинет', lambda: open_url(load_settings().get('lk') or 'https://gdman.ink'))
    tg_btn = mk_top('✈  Telegram', lambda: open_url('https://t.me/goodmanNet_bot'))
    lk_btn.grid(row=0, column=0, padx=5, sticky='ew'); tg_btn.grid(row=0, column=1, padx=5, sticky='ew')
    top.columnconfigure(0, weight=1, uniform='t'); top.columnconfigure(1, weight=1, uniform='t')

    # ----- круглая кнопка питания + ⚙ / 📋 по бокам (как в Linux) -----
    prow = tk.Frame(root, bg=BG); prow.pack(pady=(14, 4))

    def side_btn(parent, txt, cmd):
        sz = 54
        c = tk.Canvas(parent, width=sz, height=sz, bg=BG, highlightthickness=0, cursor='hand2')
        circ = c.create_oval(3, 3, sz - 3, sz - 3, fill=CARD2, outline='#33384a', width=1)
        c.create_text(sz // 2, sz // 2 + 1, text=txt, fill='#c7cdda', font=(F, 17))
        c.bind('<Button-1>', lambda e: cmd())
        c.bind('<Enter>', lambda e: c.itemconfig(circ, fill='#2c3145'))
        c.bind('<Leave>', lambda e: c.itemconfig(circ, fill=CARD2))
        return c

    gearb = side_btn(prow, '⚙', lambda: open_menu())
    gearb.pack(side='left', padx=(0, 12))
    cv = tk.Canvas(prow, width=190, height=190, bg=BG, highlightthickness=0, cursor='hand2')
    cv.pack(side='left')
    logsb = side_btn(prow, '📋', lambda: show_logs())
    logsb.pack(side='left', padx=(12, 0))
    circle = cv.create_oval(15, 15, 175, 175, fill=GRAY, outline='')
    # иконка питания рисуется линиями (символ ⏻ на Windows не всегда есть → квадрат)
    cx, cy, r = 95, 97, 34
    pico = [
        cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=112, extent=316,
                      style='arc', outline='#ffffff', width=7),
        cv.create_line(cx, cy - r - 6, cx, cy - 4, fill='#ffffff', width=7, capstyle='round'),
    ]
    try:
        _im = tk.PhotoImage(file=os.path.join(RES_DIR, 'logo.png'))
        _f = max(1, int(round(_im.width() / 82.0)))   # меньше логотип → больше зелёного фона
        st_data['logo'] = _im.subsample(_f, _f)
    except Exception:
        st_data['logo'] = None

    def set_power(on):
        cv.itemconfig(circle, fill=(GREEN if on else GRAY))
        if on and st_data['logo'] is not None:
            for i in pico: cv.itemconfigure(i, state='hidden')
            if st_data['logo_id'] is None:
                st_data['logo_id'] = cv.create_image(95, 95, image=st_data['logo'])
            cv.itemconfigure(st_data['logo_id'], state='normal')
        else:
            if st_data['logo_id'] is not None:
                cv.itemconfigure(st_data['logo_id'], state='hidden')
            for i in pico: cv.itemconfigure(i, state='normal')
    cv.bind('<Button-1>', lambda e: toggle())

    status = tk.Label(root, text='Отключено', bg=BG, fg=MUT, font=(F, 14, 'bold'),
                      compound='left', padx=6); status.pack()
    speed = tk.Label(root, text='', bg=BG, fg=MUT, font=(F, 10)); speed.pack()
    def set_status(t, color=MUT, flag=None):
        img = flag_for(flag) if flag else None
        status.config(text=t, fg=color, image=(img or ''))

    # ----- быстрые действия (как в Linux: плоские, акцентный текст) -----
    qa = tk.Frame(root, bg=BG); qa.pack(pady=(8, 2))
    def mk_qa(txt, cmd, col):
        b = tk.Label(qa, text=txt, bg=BG, fg=ACC, font=(F, 10, 'bold'), padx=8, pady=4, cursor='hand2')
        b.grid(row=0, column=col, padx=2)
        b.bind('<Button-1>', lambda e: cmd())
        b.bind('<Enter>', lambda e: b.config(bg=CARD2))
        b.bind('<Leave>', lambda e: b.config(bg=(b._onbg if getattr(b, '_on', False) else BG)))
        b._on = False; b._onbg = BG
        return b
    b_ref = mk_qa('🔄 Обновить', lambda: refresh_sub(), 0)
    b_byp = mk_qa('📱 Мимо VPN', lambda: qa_bypass(), 1)
    b_spd = mk_qa('📊 Скорость', lambda: qa_speed(), 2)
    b_kill = mk_qa('🛡 Kill switch', lambda: qa_kill(), 3)
    def set_toggle(b, on):
        b._on = on
        if on:
            b._onbg = ACC; b.config(bg=ACC, fg='#ffffff')
        else:
            b._onbg = BG; b.config(bg=BG, fg=ACC)

    # ----- карточка подписки -----
    subcard = tk.Frame(root, bg=CARD, highlightbackground='#33384a', highlightthickness=1)
    subtext = tk.Label(subcard, text='', bg=CARD, fg='#c7cdda', font=(F, 10),
                       justify='center', wraplength=380)
    subtext.pack(padx=14, pady=11)

    # ----- ошибка -----
    errfr = tk.Frame(root, bg=CARD, highlightbackground=RED, highlightthickness=1)
    errtitle = tk.Label(errfr, text='', bg=CARD, fg='#fda4a4', font=(F, 10, 'bold'),
                        wraplength=380, justify='left'); errtitle.pack(anchor='w', padx=10, pady=(8, 2))
    errtext = tk.Text(errfr, height=5, bg='#141416', fg='#fecaca', bd=0, wrap='word', font=('Consolas', 8))
    errtext.pack(fill='x', padx=10)
    ebf = tk.Frame(errfr, bg=CARD); ebf.pack(fill='x', padx=10, pady=6)
    tk.Button(ebf, text='📋 Скопировать', bg=CARD2, fg=FG, relief='flat', bd=0, font=(F, 9),
              command=lambda: (root.clipboard_clear(),
                               root.clipboard_append(errtitle['text'] + '\n' + errtext.get('1.0', 'end')))
              ).pack(side='left')
    tk.Button(ebf, text='✕', bg=CARD2, fg=FG, relief='flat', bd=0, font=(F, 9),
              command=lambda: errfr.pack_forget()).pack(side='right')
    def show_err(title, details=''):
        errtitle.config(text=title); errtext.delete('1.0', 'end'); errtext.insert('1.0', details or '')
        errfr.pack(fill='x', padx=22, pady=6)

    # ----- ввод подписки (с подсказкой над полем + плейсхолдер) -----
    setup = tk.Frame(root, bg=BG)
    tk.Label(setup, text='Вставьте сюда ссылку на подписку из личного кабинета',
             bg=BG, fg=MUT, font=(F, 10)).pack(anchor='w', pady=(0, 4))
    PH = 'gdman.ink/s/...'
    sub_entry = tk.Entry(setup, bg=CARD, fg=MUT, insertbackground=FG, relief='flat', font=(F, 11))
    sub_entry.pack(fill='x', ipady=7)
    sub_entry.insert(0, PH)
    def _ph_in(e):
        if sub_entry.get() == PH:
            sub_entry.delete(0, 'end'); sub_entry.config(fg=FG)
    def _ph_out(e):
        if not sub_entry.get().strip():
            sub_entry.insert(0, PH); sub_entry.config(fg=MUT)
    sub_entry.bind('<FocusIn>', _ph_in); sub_entry.bind('<FocusOut>', _ph_out)
    tk.Button(setup, text='Подключить подписку', command=lambda: save_sub(), bg=ACC, fg='#fff',
              relief='flat', bd=0, font=(F, 11, 'bold'), cursor='hand2', activebackground='#6f9df2'
              ).pack(fill='x', pady=(9, 0), ipady=7)

    # ----- список серверов (Treeview с иконками флагов слева) -----
    from tkinter import ttk
    _style = ttk.Style()
    try: _style.theme_use('clam')
    except Exception: pass
    _style.configure('GM.Treeview', background=CARD, fieldbackground=CARD, foreground=FG,
                     borderwidth=0, rowheight=32, font=(F, 11))
    _style.map('GM.Treeview', background=[('selected', ACC)], foreground=[('selected', '#ffffff')])
    _style.layout('GM.Treeview', [('GM.Treeview.treearea', {'sticky': 'nswe'})])  # без заголовка
    listfr = tk.Frame(root, bg=CARD)
    srv_tree = ttk.Treeview(listfr, show='tree', style='GM.Treeview', selectmode='browse')
    srv_tree.column('#0', width=340, stretch=True)
    srv_tree.pack(fill='both', expand=True, padx=8, pady=8)
    srv_tree.bind('<<TreeviewSelect>>', lambda e: on_pick())

    # ---------- логика ----------
    def refresh_servers():
        for it in srv_tree.get_children():
            srv_tree.delete(it)
        stt = load_settings()
        for i, s in enumerate(stt.get('servers', [])):
            img = flag_for(_code_from_name(s['name']))
            srv_tree.insert('', 'end', iid=str(i), text='  ' + _clean_name(s['name']),
                            image=(img or ''))
        sel = stt.get('selected', 0)
        servers = stt.get('servers', [])
        if 0 <= sel < len(servers):
            srv_tree.selection_set(str(sel)); srv_tree.see(str(sel))

    def sync_visibility():
        stt = load_settings(); has = bool(stt.get('servers'))
        if has:
            setup.pack_forget(); listfr.pack(fill='both', expand=True, padx=22, pady=(8, 6))
        else:
            listfr.pack_forget(); setup.pack(fill='x', padx=22, pady=8)
        set_toggle(b_byp, stt.get('bypass_ru', True))
        set_toggle(b_kill, stt.get('killswitch', False))
        lines = []
        acc = stt.get('account', '')
        if acc: lines.append('Личный кабинет: ' + acc)
        lines += [cap_first(p) for p in (stt.get('announce', '') or '').split(' · ')
                  if p.strip() and 'happ' not in p.lower()]
        servers = stt.get('servers', []); ss = stt.get('selected', 0)
        name = servers[ss]['name'] if 0 <= ss < len(servers) else ''
        ti = stt.get('traffic') or {}
        if 'plus' in name.lower() and ti.get('total'):
            used = ti.get('up', 0) + ti.get('down', 0)
            lines.append('Осталось трафика: %s из %s' % (fmt_bytes(max(0, ti['total'] - used)), fmt_bytes(ti['total'])))
        if lines:
            subtext.config(text='\n'.join(lines)); subcard.pack(fill='x', padx=22, pady=6, after=qa)
        else:
            subcard.pack_forget()

    def refresh_state():
        was = st_data['connected']
        st_data['connected'] = is_connected()
        set_power(st_data['connected'])
        if st_data['busy']:
            sync_visibility(); return
        if st_data['connected']:
            g = st_data['geo']
            set_status(g.get('txt') if g else '✅ Подключено', GREEN, g.get('code') if g else None)
            if not was or not st_data['geo']:
                def geo():
                    g = exit_geo()
                    if g.get('ok'):
                        code = (g.get('country_code') or '').lower()
                        txt = ('Подключено · %s' % (g.get('ip') or '')).strip(' ·')
                        st_data['geo'] = {'txt': txt, 'code': code}
                        ui(lambda: st_data['connected'] and not st_data['busy'] and set_status(txt, GREEN, code))
                threading.Thread(target=geo, daemon=True).start()
        else:
            st_data['geo'] = ''
            if not st_data['speed_running']:
                speed.config(text='')
            set_status('Отключено', MUT)
        sync_visibility()

    def toggle():
        if st_data['busy']:
            return
        stt = load_settings()
        if not stt.get('servers'):
            sub_entry.focus_set(); return
        st_data['busy'] = True; errfr.pack_forget()
        set_status('Отключение…' if st_data['connected'] else 'Подключение…', FG)
        def work():
            if st_data['connected']:
                do_disconnect(); ok, t, d = True, '', ''
            else:
                ok, t, d = do_connect()
            def done():
                st_data['busy'] = False
                if not ok: show_err(t, d)
                refresh_state()
            ui(done)
        threading.Thread(target=work, daemon=True).start()

    def on_pick():
        sel = srv_tree.selection()
        if not sel: return
        try: i = int(sel[0])
        except Exception: return
        cur = load_settings().get('selected', 0)
        if i == cur: return
        set_status('Переключение…', FG)
        threading.Thread(target=lambda: (do_select(i), ui(refresh_state)), daemon=True).start()

    def refresh_sub():
        stt = load_settings()
        if not stt.get('sub'): return
        errfr.pack_forget(); set_status('Обновление подписки…', FG)
        url = stt['sub']
        def work():
            try:
                servers, e, meta = sub_fetch(url)
            except Exception as ex:
                ui(lambda: (show_err('Не удалось обновить подписку', str(ex)), refresh_state())); return
            def done():
                if e: show_err(e)
                elif servers:
                    apply_sub(url, servers, meta); refresh_servers()
                refresh_state()
            ui(done)
        threading.Thread(target=work, daemon=True).start()

    def save_sub():
        url = sub_entry.get().strip()
        if not url or url == PH: return
        errfr.pack_forget(); set_status('Загрузка подписки…', FG)
        def work():
            try:
                servers, e, meta = sub_fetch(url)
            except Exception as ex:
                ui(lambda: (show_err('Не удалось загрузить подписку', str(ex)), refresh_state())); return
            def done():
                if e: show_err(e)
                elif not servers: show_err('Подписка пуста или неверная ссылка')
                else:
                    stt = load_settings(); stt['selected'] = 0; apply_sub(url, servers, meta, stt)
                    refresh_servers(); sync_visibility()
                refresh_state()
            ui(done)
        threading.Thread(target=work, daemon=True).start()

    def qa_bypass():
        stt = load_settings(); stt['bypass_ru'] = not stt.get('bypass_ru', True); save_settings(stt)
        sync_visibility()
        if is_connected():
            set_status('Переключение…', FG)
            threading.Thread(target=lambda: (write_sys_config(stt['servers'][stt.get('selected', 0)]),
                                             svc('restart'), ui(refresh_state)), daemon=True).start()

    def qa_kill():
        stt = load_settings(); want = not stt.get('killswitch', False)
        if want and not kill_unit_exists():
            show_err('Kill Switch', 'На Windows пока не поддерживается.'); return
        stt['killswitch'] = want; save_settings(stt); sync_visibility()
        if is_connected():
            if want:
                ip = ''
                try: ip = json.load(open(SYS_CONFIG))['outbounds'][0].get('server', '')
                except Exception: pass
                ok, d = killswitch(True, ip)
                if not ok: show_err('Kill Switch', d)
            else:
                killswitch(False)

    def qa_speed():
        if st_data['speed_running']: return
        if not is_connected():
            speed.config(text='📊 Сначала подключитесь'); return
        st_data['speed_running'] = True; speed.config(text='📊 Измеряю скорость…')
        def work():
            import time as _t
            mbps = None
            for u in ('https://speed.cloudflare.com/__down?bytes=20000000',
                      'http://cachefly.cachefly.net/10mb.test'):
                try:
                    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 gm'})
                    t0 = _t.time(); total = 0
                    with urllib.request.urlopen(req, timeout=20) as r:
                        while _t.time() - t0 < 10:
                            c = r.read(65536)
                            if not c: break
                            total += len(c)
                    if total > 500000:
                        mbps = total * 8 / max(0.15, _t.time() - t0) / 1e6; break
                except Exception:
                    continue
            def done():
                st_data['speed_running'] = False
                speed.config(text=('📊 %.1f Мбит/с' % mbps) if mbps else '📊 —')
            ui(done)
        threading.Thread(target=work, daemon=True).start()

    def logout_sub():
        from tkinter import messagebox
        if not messagebox.askyesno('Выйти из подписки?',
                'VPN будет отключён, подписка удалена из приложения. Её можно добавить снова.'):
            return
        def work():
            if is_connected(): do_disconnect()
            stt = load_settings()
            for k in ('sub', 'servers', 'selected', 'lk', 'account', 'announce', 'traffic'):
                stt.pop(k, None)
            stt['servers'] = []; stt['selected'] = 0; save_settings(stt)
            def done():
                sub_entry.delete(0, 'end'); sub_entry.insert(0, PH); sub_entry.config(fg=MUT)
                refresh_servers(); sync_visibility(); refresh_state()
            ui(done)
        threading.Thread(target=work, daemon=True).start()

    def show_logs():
        w = st_data.get('logwin')
        if w is not None:
            try:
                if w.winfo_exists():
                    w.lift(); load_logs(); return
            except Exception:
                pass
        w = tk.Toplevel(root); w.title('Логи VPN'); w.configure(bg=BG); w.geometry('700x520')
        st_data['logwin'] = w
        txt = tk.Text(w, bg='#141416', fg='#c9d8f3', bd=0, wrap='word', font=('Consolas', 9))
        txt.pack(fill='both', expand=True, padx=10, pady=10)
        st_data['logtext'] = txt
        bf = tk.Frame(w, bg=BG); bf.pack(fill='x', padx=10, pady=(0, 10))
        tk.Button(bf, text='🔄 Обновить', command=load_logs, bg=CARD2, fg=FG, relief='flat', bd=0
                  ).pack(side='left', padx=4)
        tk.Button(bf, text='📋 Скопировать всё', bg=CARD2, fg=FG, relief='flat', bd=0,
                  command=lambda: (root.clipboard_clear(), root.clipboard_append(txt.get('1.0', 'end')))
                  ).pack(side='left', padx=4)
        load_logs()

    def load_logs():
        t = st_data.get('logtext')
        if not t: return
        t.delete('1.0', 'end'); t.insert('1.0', 'Загрузка…')
        def work():
            logs = svc_logs()
            ui(lambda: (t.delete('1.0', 'end'), t.insert('1.0', logs)))
        threading.Thread(target=work, daemon=True).start()

    def open_menu():
        m = tk.Menu(root, tearoff=0, bg=CARD, fg=FG, activebackground=ACC, activeforeground='#fff')
        def change_sub():
            setup.pack(fill='x', padx=22, pady=8)
            cur = load_settings().get('sub', '')
            sub_entry.delete(0, 'end'); sub_entry.insert(0, cur or PH)
            sub_entry.config(fg=(FG if cur else MUT))
        m.add_command(label='🔗 Сменить подписку', command=change_sub)
        m.add_command(label='🚪 Выйти из подписки', command=logout_sub)
        m.add_command(label='📋 Логи VPN', command=show_logs)
        try: m.tk_popup(root.winfo_pointerx(), root.winfo_pointery())
        finally: m.grab_release()

    def tick():
        if not st_data['busy']:
            threading.Thread(target=lambda: ui(refresh_state), daemon=True).start()
        root.after(4000, tick)

    threading.Thread(target=ensure_win_shortcut, daemon=True).start()
    threading.Thread(target=background_refresh, daemon=True).start()
    refresh_servers(); sync_visibility(); refresh_state()
    root.after(4000, tick)
    root.mainloop()

def main():
    if IS_WIN:
        try:
            run_tk(); return
        except Exception as e:
            print('tkinter недоступен (%s) — web-режим' % e)
            run_web(); return
    if '--web' not in sys.argv:
        try:
            import gi  # noqa: F401
            run_gtk()
            return
        except Exception as e:
            print('GTK недоступен (%s) — tkinter/web' % e)
    try:
        run_tk(); return
    except Exception:
        run_web()


if __name__ == '__main__':
    main()
