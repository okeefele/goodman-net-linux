#!/usr/bin/env bash
# GoodMan Net — установщик для Linux.
# Использование:  wget -qO- https://gdman.ink/dl/install.sh | sudo bash
set -e

APP=/opt/goodman-net
CFG=/etc/goodman-net
BASE=https://gdman.ink/dl
USER_REAL="${SUDO_USER:-$(id -un)}"

if [ "$(id -u)" != "0" ]; then
  echo "Запустите через sudo:  wget -qO- $BASE/install.sh | sudo bash"; exit 1
fi

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) PKG=goodman-net-linux-amd64.tar.gz ;;
  aarch64|arm64) PKG=goodman-net-linux-arm64.tar.gz ;;
  *) echo "Архитектура $ARCH пока не поддерживается. Напишите в поддержку @GoodMan_sup"; exit 1 ;;
esac

echo "→ Скачиваю GoodMan Net ($ARCH)…"
mkdir -p "$APP" "$CFG"
TMP=$(mktemp -d)
wget -qO "$TMP/pkg.tgz" "$BASE/$PKG"
tar -xzf "$TMP/pkg.tgz" -C "$APP"
chmod +x "$APP/sing-box" "$APP/precheck.sh" 2>/dev/null || true
rm -rf "$TMP"

# каталог конфига — доступен на запись пользователю (туда пишет GUI, читает сервис от root)
chown "$USER_REAL":"$USER_REAL" "$CFG"
chmod 755 "$CFG"

echo "→ Ставлю системный сервис…"
cat >/etc/systemd/system/goodman-net.service <<EOF
[Unit]
Description=GoodMan Net VPN
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
# перед стартом глушим чужие VPN (Happ) и чистим их tun/маршруты
ExecStartPre=-/bin/sh $APP/precheck.sh
ExecStart=$APP/sing-box run -c $CFG/config.json
# системный DNS (systemd-resolved) заворачиваем в туннель: иначе консольные программы
# резолвят через физический интерфейс мимо VPN (браузеры с DoH работают, консоль — нет).
# 172.19.0.2 маршрутизируется в tun -> sing-box перехватывает (hijack-dns) и отвечает по DoH.
ExecStartPost=/bin/sh -c 'command -v resolvectl >/dev/null || exit 0; for i in \$(seq 1 20); do ip link show gmtun0 >/dev/null 2>&1 && break; sleep 0.3; done; resolvectl dns gmtun0 172.19.0.2 2>/dev/null; resolvectl domain gmtun0 "~." 2>/dev/null; resolvectl default-route gmtun0 true 2>/dev/null; exit 0'
Restart=on-failure
RestartSec=2
[Install]
WantedBy=multi-user.target
EOF

# kill switch: отдельный root-юнит с nftables (управляется из приложения)
chmod +x "$APP/killswitch.sh" 2>/dev/null || true
cat >/etc/systemd/system/goodman-net-kill.service <<EOF
[Unit]
Description=GoodMan Net Kill Switch (block internet without VPN)
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh $APP/killswitch.sh up
ExecStop=/bin/sh $APP/killswitch.sh down
[Install]
WantedBy=multi-user.target
EOF

# polkit: разрешаем пользователю управлять ИМЕННО этими сервисами без пароля
cat >/etc/polkit-1/rules.d/49-goodman-net.rules <<EOF
polkit.addRule(function(action, subject) {
  if (action.id == "org.freedesktop.systemd1.manage-units" &&
      (action.lookup("unit") == "goodman-net.service" ||
       action.lookup("unit") == "goodman-net-kill.service")) {
    return polkit.Result.YES;
  }
});
EOF

systemctl daemon-reload

echo "→ Ставлю команду запуска и ярлык…"
cat >/usr/local/bin/goodman-net <<EOF
#!/bin/sh
exec python3 $APP/gmapp.py "\$@"
EOF
chmod +x /usr/local/bin/goodman-net

# имя файла = GTK application_id — иначе GNOME-док показывает шестерёнку вместо логотипа
rm -f /usr/share/applications/goodman-net.desktop
cat >/usr/share/applications/ink.gdman.goodmannet.desktop <<EOF
[Desktop Entry]
Name=GoodMan Net
Comment=VPN
Exec=goodman-net
Icon=$APP/logo.png
Terminal=false
Type=Application
Categories=Network;Security;
StartupWMClass=ink.gdman.goodmannet
EOF
update-desktop-database /usr/share/applications 2>/dev/null || true

# python3-gi (GTK) для нативного окна — ставим, если нет (иначе будет web-режим)
if ! python3 -c 'import gi' 2>/dev/null; then
  echo "→ Ставлю python3-gi (нативное окно)…"
  apt-get install -y -qq python3-gi gir1.2-gtk-3.0 2>/dev/null \
    || dnf install -y -q python3-gobject gtk3 2>/dev/null \
    || pacman -S --noconfirm --quiet python-gobject gtk3 2>/dev/null \
    || zypper --non-interactive install python3-gobject-Gdk typelib-1_0-Gtk-3_0 2>/dev/null \
    || echo "  (не удалось поставить python3-gi — приложение откроется в web-режиме)"
fi

echo ""
echo "✅ Установлено!"
echo "   Запуск:  goodman-net   (или через меню приложений)"
echo "   Вставьте ссылку на подписку из личного кабинета — и жмите большую кнопку."
