#!/bin/sh
# GoodMan Net — kill switch (nftables). Запускается root-юнитом goodman-net-kill.service.
# up: блокирует весь исходящий трафик, кроме loopback, локальных сетей, нашего VPN-сервера
#     и интерфейса туннеля gmtun0. down: снимает блокировку.
set -e
ENV=/etc/goodman-net/killswitch.env
[ -f "$ENV" ] && . "$ENV"

case "$1" in
  up)
    nft delete table inet gmkill 2>/dev/null || true
    nft add table inet gmkill
    nft add chain inet gmkill out '{ type filter hook output priority 0 ; policy drop ; }'
    nft add rule inet gmkill out oifname "lo" accept
    nft add rule inet gmkill out oifname "gmtun0" accept
    # локальные сети (DHCP, роутер, LAN)
    nft add rule inet gmkill out ip daddr '{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 255.255.255.255 }' accept
    nft add rule inet gmkill out ip6 daddr '{ fe80::/10, ff00::/8 }' accept
    # сам VPN-сервер (туннель должен пробиться наружу)
    if [ -n "$SERVER_IP" ]; then
      nft add rule inet gmkill out ip daddr "$SERVER_IP" accept
    fi
    ;;
  down)
    nft delete table inet gmkill 2>/dev/null || true
    ;;
  *)
    echo "usage: $0 up|down"; exit 1 ;;
esac
