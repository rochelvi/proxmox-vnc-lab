# Proxmox VNC Lab

Небольшой сервис для выдачи стажёрам клонированных ВМ из шаблона Proxmox VE и
подключения к их консолям в браузере через noVNC.

## Возможности

- локальные пользователи с JWT-аутентификацией;
- ограничение количества ВМ на пользователя;
- linked clone по умолчанию (full clone включается настройкой);
- запуск, остановка и удаление ВМ;
- проксирование VNC WebSocket через backend, поэтому браузеру не нужен прямой
  доступ к PVE;
- расширяемая точка для LDAP/OAuth в `app/auth_providers.py`.

## Подготовка Proxmox

Создайте шаблон ВМ, установите в нём нужную ОС и инструменты, затем выключите
его и преобразуйте в Template. Шаблон должен быть доступен на указанном узле.

Для token auth создайте пользователя и API token. Минимальные права токена:
`VM.Clone`, `VM.Config`, `VM.PowerMgmt`, `VM.Console`. Для full clone добавьте
`Datastore.AllocateSpace` на целевом storage.

Пример (проверьте домен realm и пути в своей установке):

```bash
pveum user add interns@pve
pveum role add InternVncLab -privs "VM.Clone,VM.Config,VM.PowerMgmt,VM.Console"
pveum acl modify /vms --users interns@pve --roles InternVncLab
pveum user token add interns@pve vmlab --privsep 0
```

Сохраните показанный token secret: повторно получить его нельзя. Если используете
full clone, выдайте `Datastore.AllocateSpace` на storage, например:

```bash
pveum role modify InternVncLab -privs "VM.Clone,VM.Config,VM.PowerMgmt,VM.Console,Datastore.AllocateSpace"
pveum acl modify /storage/local --users interns@pve --roles InternVncLab
```

## Запуск локально

Нужны Python 3.11+ и [uv](https://docs.astral.sh/uv/):

```bash
uv python install 3.11
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
# заполните PVE_* и JWT_SECRET
python -m app.cli create-user intern1 'strong-password'
python -m app.cli create-user admin 'another-strong-password' --admin
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Откройте `http://localhost:8000/login.html`.

## Настройка

Все переменные перечислены в `.env.example`. `CLONE_FULL=false` использует
linked clone. При `CLONE_FULL=true` сервис передаст `storage` (если заполнен
`CLONE_STORAGE`) и `pool` в API PVE. `CLONE_VMID_MIN/MAX` задают диапазон
выдаваемых ID.

По умолчанию используется API token:
`PVE_TOKEN_ID=interns@pve!vmlab` и `PVE_TOKEN_SECRET=...`.
Если одновременно заданы `PVE_USER` и `PVE_PASSWORD`, WebSocket VNC предпочитает
получить ticket через `/access/ticket` и отправляет `PVEAuthCookie`: некоторые
версии PVE отклоняют API-token заголовок на `vncwebsocket`. Для token auth
используется `Authorization: PVEAPIToken=...`. Этот выбор сделан именно для
совместимости с различными версиями PVE; пароль хранится только в окружении.

## Docker Compose

```bash
cp .env.example .env
# отредактируйте .env
docker compose up --build -d
docker compose exec proxmox-vnc-lab python -m app.cli create-user intern1 'strong-password'
```

Каталог `./data` монтируется в контейнер и хранит SQLite. Контейнер работает не
от root. Для production используйте TLS перед сервисом и длинный случайный
`JWT_SECRET`.

## noVNC и air-gapped установка

`static/console.html` импортирует ESM noVNC версии
`https://cdn.jsdelivr.net/npm/@novnc/novnc@1.6.0/lib/rfb.js`. Этот URL и точная
версия проверены как часть release-публикации noVNC. В закрытой сети скачайте
тот же пакет и разместите его в `static/vendor/novnc`, после чего замените
импорт на `/vendor/novnc/lib/rfb.js` (включая необходимые зависимости).

## API и проверка

Основные маршруты: `POST /api/auth/login`, `GET /api/auth/me`, `GET/POST
/api/vms`, `POST /api/vms/{vmid}/start|stop`, `DELETE /api/vms/{vmid}` и
`GET /api/vms/{vmid}/vnc`. WebSocket использует
`/api/vms/{vmid}/ws?port=...&vncticket=...&token=<JWT>`.

```bash
ruff check .
python -m compileall app
pytest
```

Тесты не подключаются к реальному PVE: сервис подменён stub-реализацией. Полная
проверка clone/start/VNC требует работающего Proxmox VE, корректных privileges,
шаблона и сетевого доступа к PVE.
