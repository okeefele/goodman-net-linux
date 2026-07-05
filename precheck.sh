#!/bin/sh
# GoodMan Net — предстартовая очистка (ExecStartPre, от root).
# Глушит чужие VPN-клиенты (Happ и т.п.) и сносит их остатки (tun, таблицы, правила),
# чтобы не конфликтовали маршруты. Наш туннель поднимается уже на чистой машине.

# 1) мягко (даёт sing-box/xray Happ убрать свои маршруты сами), потом жёстко
pkill -TERM -f '/opt/happ' 2>/dev/null || true
sleep 2
pkill -KILL -f '/opt/happ' 2>/dev/null || true

# 2) удаляем оставшиеся чужие tun/tap (кроме нашего gmtun0)
for i in $(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | sed 's/@.*//' \
           | grep -E '^(tun|tap)' | grep -v '^gmtun0$'); do
    ip link delete "$i" 2>/dev/null || true
done

# 3) чистим известную таблицу/правила sing-box Happ (2022), если остались
ip route flush table 2022 2>/dev/null || true
n=0
while ip rule del lookup 2022 2>/dev/null; do
    n=$((n+1)); [ "$n" -gt 20 ] && break
done

exit 0
