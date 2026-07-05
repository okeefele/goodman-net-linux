# GoodMan Net — Linux

Десктоп-клиент VPN **GoodMan Net** для Linux. Приложение на Python (`gmapp.py`) с нативным окном
(GTK) поверх [sing-box](https://github.com/SagerNet/sing-box). Работает как systemd-сервис,
kill switch на nftables. Подписку из личного кабинета вставляете один раз — дальше одна большая кнопка.

Та же кодовая база используется для Windows и macOS (`goodman-net-desktop`, `goodman-net-macOS`).

## Установка

Одной командой (нужен 64-бит Linux с systemd — Ubuntu, Debian, Fedora, Arch, Mint и др.):
```
wget -qO- https://gdman.ink/dl/install.sh | sudo bash
```

## Файлы

```
gmapp.py        приложение (UI + управление туннелем)
gmcore.py       разбор подписки, генерация конфигурации sing-box, замер скорости
ui.html         web-режим (fallback, если нет python3-gi/GTK)
install.sh      установщик: сервис, polkit, ярлык, DNS через туннель
precheck.sh     глушит чужие VPN (Happ) перед стартом
killswitch.sh   kill switch на nftables (блок интернета без VPN)
flags/          флаги стран, logo.png — иконка
```

## Как это работает

- `goodman-net.service` — systemd-юнит, запускает `sing-box run`
- `goodman-net-kill.service` — kill switch (nftables), управляется из приложения
- polkit-правило разрешает пользователю управлять этими двумя юнитами без пароля
- DNS заворачивается в туннель через `resolvectl` (иначе консольные программы резолвят мимо VPN)

## Безопасность

Никаких ключей/токенов в коде нет — подписка вводится пользователем. Клиент общается только с
VPN-серверами GoodMan Net. sing-box — под GPLv3.
