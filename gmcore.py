#!/usr/bin/env python3
"""GoodMan Net — ядро десктоп-клиента: разбор подписки + генерация sing-box конфига.
Схема конфига под sing-box >= 1.12 (новый формат dns.servers, без detour на пустой direct)."""
import base64, json, socket, urllib.parse, urllib.request

# отдельная таблица/правила маршрутизации — чтобы не конфликтовать с другими VPN (Happ и т.п.)
ROUTE_TABLE = 2233
ROUTE_RULE = 8300


def _parse_userinfo(v):
    """Заголовок Subscription-Userinfo: 'upload=..; download=..; total=..' -> {up,down,total} в байтах."""
    out = {'up': 0, 'down': 0, 'total': 0}
    for part in (v or '').replace(',', ';').split(';'):
        if '=' in part:
            k, _, val = part.partition('=')
            k = k.strip().lower()
            try:
                n = int(val.strip())
            except Exception:
                continue
            if k == 'upload': out['up'] = n
            elif k == 'download': out['down'] = n
            elif k == 'total': out['total'] = n
    return out


def _b64hdr(v):
    """Заголовки Happ-формата: 'base64:...' -> текст."""
    if v and v.startswith('base64:'):
        try:
            return base64.b64decode(v[7:] + '===').decode('utf-8', 'replace')
        except Exception:
            return ''
    return v or ''


def fetch_subscription(url, hwid='', os_name='linux', model=''):
    """Принимает полный sub-URL или короткий токен. Возвращает (servers, meta).
    meta: lk (ссылка в личный кабинет), account (ID ЛК), announce (статус подписки).
    Шлёт x-hwid (учёт устройств на сервере, как Happ) — иначе сервер отдаёт заглушку."""
    if not url.startswith('http'):
        url = 'https://gdman.ink/s/' + url.strip().strip('/')
    headers = {
        'User-Agent': 'Happ/2.18.3/GoodManNet-Desktop',
        'x-hwid': hwid or '',
        'x-device-os': os_name,
        'x-device-model': model or 'Desktop',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode('utf-8', 'replace')
        h = r.headers
        lk = h.get('profile-web-page-url', '') or ''
        meta = {
            'lk': lk,
            'account': lk.rstrip('/').rsplit('/', 1)[-1] if '/lk/' in lk else '',
            'announce': _b64hdr(h.get('announce', '')),
            'traffic': _parse_userinfo(h.get('subscription-userinfo', '')),
        }
    try:
        dec = base64.b64decode(raw + '===').decode('utf-8', 'replace')
        if 'vless://' in dec:
            raw = dec
    except Exception:
        pass
    servers = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith('vless://'):
            s = parse_vless(line)
            if s:
                servers.append(s)
    return servers, meta


def parse_vless(link):
    u = urllib.parse.urlparse(link)
    q = dict(urllib.parse.parse_qsl(u.query))
    name = urllib.parse.unquote(u.fragment) or 'GoodMan'
    return {
        'name': name, 'uuid': u.username, 'host': u.hostname, 'port': u.port or 443,
        'security': q.get('security', 'tls'), 'sni': q.get('sni', u.hostname),
        'type': q.get('type', 'tcp'), 'path': urllib.parse.unquote(q.get('path', '')),
        'ws_host': q.get('host', u.hostname), 'flow': q.get('flow', ''),
        'pbk': q.get('pbk', ''), 'sid': q.get('sid', ''), 'fp': q.get('fp', 'chrome'),
    }


def resolve_ip(host):
    """Резолвим адрес сервера заранее (пока VPN ещё не поднят) — уходим от курицы-и-яйца с DNS."""
    try:
        for fam, *_, sa in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM):
            return sa[0]
    except Exception:
        pass
    return None


def make_outbound(s, tag='proxy', server=None):
    out = {'type': 'vless', 'tag': tag, 'server': server or s['host'], 'server_port': int(s['port']),
           'uuid': s['uuid'], 'packet_encoding': 'xudp'}
    if s['flow']:
        out['flow'] = s['flow']
    if s['security'] == 'tls':
        out['tls'] = {'enabled': True, 'server_name': s['sni'],
                      'utls': {'enabled': True, 'fingerprint': s['fp']}}
    elif s['security'] == 'reality':
        out['tls'] = {'enabled': True, 'server_name': s['sni'],
                      'utls': {'enabled': True, 'fingerprint': s['fp']},
                      'reality': {'enabled': True, 'public_key': s['pbk'], 'short_id': s['sid']}}
    if s['type'] == 'ws':
        out['transport'] = {'type': 'ws', 'path': s['path'],
                            'headers': {'Host': s['ws_host']}}
    return out


def config_socks_test(s, port=10999):
    """Конфиг для проверки движка: socks-инбаунд -> vless-аутбаунд (без root/tun)."""
    return {
        'log': {'level': 'warn'},
        'dns': {'servers': [{'type': 'udp', 'tag': 'localdns', 'server': '8.8.8.8'}], 'final': 'localdns'},
        'inbounds': [{'type': 'socks', 'tag': 'in', 'listen': '127.0.0.1', 'listen_port': port}],
        'outbounds': [make_outbound(s, 'proxy'), {'type': 'direct', 'tag': 'direct'}],
    }


# «Мимо VPN»: ru-домены напрямую (банки и госсервисы блокируют заграничные IP)
BYPASS_SUFFIXES = ['.ru', '.su', '.xn--p1ai']   # .xn--p1ai = .рф


def config_tun(s, bypass_ru=True):
    """Полный VPN-конфиг: tun (auto_route) -> vless. Запускается сервисом от root.
    Адрес сервера пиннится по IP на момент подключения (DNS дальше идёт через туннель).
    bypass_ru: сайты .ru/.рф идут напрямую (банки/госуслуги работают без танцев)."""
    ip = resolve_ip(s['host'])
    dns_servers = [{'type': 'https', 'tag': 'proxydns', 'server': '1.1.1.1', 'detour': 'proxy'}]
    dns_rules = []
    need_localdns = bypass_ru or not ip
    if need_localdns:
        dns_servers.append({'type': 'udp', 'tag': 'localdns', 'server': '8.8.8.8'})
    if not ip:
        # не смогли отрезолвить заранее — оставляем домен и локальный DNS для него
        dns_rules.append({'domain': [s['host']], 'server': 'localdns'})
    route_rules = [
        {'action': 'sniff'},
        {'protocol': 'dns', 'action': 'hijack-dns'},
        {'ip_is_private': True, 'outbound': 'direct'},
    ]
    if bypass_ru:
        dns_rules.append({'domain_suffix': BYPASS_SUFFIXES, 'server': 'localdns'})
        route_rules.append({'domain_suffix': BYPASS_SUFFIXES, 'outbound': 'direct'})
    cfg = {
        'log': {'level': 'warn', 'timestamp': True},
        'dns': {'servers': dns_servers, 'final': 'proxydns', 'strategy': 'ipv4_only'},
        'inbounds': [{
            'type': 'tun', 'tag': 'tun-in', 'interface_name': 'gmtun0',
            'address': ['172.19.0.1/30'], 'mtu': 1500, 'auto_route': True,
            'strict_route': True, 'stack': 'gvisor',
            'iproute2_table_index': ROUTE_TABLE, 'iproute2_rule_index': ROUTE_RULE,
        }],
        'outbounds': [
            make_outbound(s, 'proxy', server=ip),
            {'type': 'direct', 'tag': 'direct'},
        ],
        'route': {
            'rules': route_rules,
            'final': 'proxy', 'auto_detect_interface': True,
        },
    }
    if need_localdns:
        # direct-даилы (мимо VPN) резолвим локальным DNS
        cfg['route']['default_domain_resolver'] = 'localdns'
    if dns_rules:
        cfg['dns']['rules'] = dns_rules
    return cfg
