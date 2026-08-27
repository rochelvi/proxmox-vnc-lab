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
uv pip install -r requirements-dev.txt
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

Несколько шаблонов задаются через allowlist `TEMPLATES`:
`TEMPLATES=9000:Ubuntu 22.04,9001:Debian 12`. Пробелы вокруг записей
игнорируются, но каждая запись обязана иметь положительный числовой VMID,
двоеточие и непустой label; ошибки конфигурации приводят к явной ошибке при
старте. Если `TEMPLATES` не задан, используется старый `TEMPLATE_VMID` с
label `template-<vmid>`. `GET /api/templates` требует авторизацию и не
обращается к PVE. При создании ВМ клиент может отправить
`{"template_vmid": 9001}`; VMID проверяется только по этой allowlist.
У существующих записей `template_vmid` и label могут быть `NULL`.

`init_db()` идемпотентно добавляет эти две колонки в старую SQLite-таблицу
через `ALTER TABLE`, поэтому отдельный migration runner для этого изменения
не нужен.

По умолчанию используется API token:
`PVE_TOKEN_ID=interns@pve!vmlab` и `PVE_TOKEN_SECRET=...`.
Если одновременно заданы `PVE_USER` и `PVE_PASSWORD`, WebSocket VNC предпочитает
получить ticket через `/access/ticket` и отправляет `PVEAuthCookie`: некоторые
версии PVE отклоняют API-token заголовок на `vncwebsocket`. Для token auth
используется `Authorization: PVEAPIToken=...`. Этот выбор сделан именно для
совместимости с различными версиями PVE; пароль хранится только в окружении.

## Аутентификация через FreeIPA / LDAP

Для переключения аутентификации на FreeIPA / LDAP установите в `.env`:

```bash
AUTH_PROVIDER=freeipa
FREEIPA_SERVER=ipa.example.local
FREEIPA_PORT=636
FREEIPA_USE_SSL=true
FREEIPA_BASE_DN=dc=example,dc=local

# По умолчанию проверяются только пользователи, уже добавленные в локальную БД.
# Если нужно автоматически создавать пользователя при первом успешном входе:
FREEIPA_AUTO_CREATE_USER=false

# Опционально: проверка прав администратора по группе в FreeIPA
FREEIPA_ADMIN_GROUP=admins

# Опционально: сервисный аккаунт для поиска пользователей (если анонимный/прямой bind не подходит)
# FREEIPA_BIND_DN=uid=binduser,cn=sysaccounts,cn=etc,dc=example,dc=local
# FREEIPA_BIND_PASSWORD=bindpassword
```

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
`https://cdn.jsdelivr.net/gh/novnc/noVNC@v1.6.0/core/rfb.js`. Важно: npm-путь
`@novnc/novnc/.../lib/rfb.js` содержит CommonJS-сборку и для браузерного ESM
импорта не подходит. В закрытой сети скачайте ESM-исходники из каталога noVNC
`core/` (со всеми относительными зависимостями), разместите их в
`static/vendor/novnc/core/` и замените импорт на `/vendor/novnc/core/rfb.js`.

## API и проверка

Основные маршруты: `POST /api/auth/login`, `GET /api/auth/me`, `POST
/api/auth/password`, `GET/POST /api/vms`, `POST /api/vms/{vmid}/start|stop`,
`DELETE /api/vms/{vmid}` и `GET /api/vms/{vmid}/vnc`. WebSocket использует
`/api/vms/{vmid}/ws?port=...&vncticket=...&token=<JWT>`.

`POST /api/auth/password` принимает `{"current_password": ..., "new_password":
...}` (новый пароль не короче 8 символов) и работает только при
`AUTH_PROVIDER=local`; в UI кнопка «Изменить пароль» скрывается, если смена
пароля недоступна. Тема оформления (светлая/тёмная) переключается кнопкой в
шапке и сохраняется в `localStorage`, по умолчанию берётся системная
`prefers-color-scheme`.

```bash
ruff check .
python -m compileall app
pytest
```

Для production достаточно установить только `requirements.txt`; `pytest` и
`ruff` находятся в `requirements-dev.txt`.

Запускайте `uvicorn` из корня репозитория: `DATABASE_URL=sqlite:///./data/app.db`
и `StaticFiles(directory="static")` используют текущий каталог. Для абсолютного
пути SQLite используйте четыре слеша, например
`DATABASE_URL=sqlite:////var/lib/proxmox-vnc-lab/app.db`.

Тесты не подключаются к реальному PVE: сервис подменён stub-реализацией. Полная
проверка clone/start/VNC требует работающего Proxmox VE, корректных privileges,
шаблона и сетевого доступа к PVE.
