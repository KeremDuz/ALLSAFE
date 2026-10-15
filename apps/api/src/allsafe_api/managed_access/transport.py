"""One bounded SSH PTY per reserved administrator session; no shell in the agent."""

import asyncio
import hmac
import json
import logging
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import anyio
import asyncssh
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from allsafe_api.managed_access.configuration import (
    ConfigurationError,
    ResolvedProfile,
    no_duplicates,
    resolve_profile,
)
from allsafe_api.managed_access.models import TerminalSession
from allsafe_api.managed_access.schemas import INPUT_ADAPTER, Ack, Hello, Input
from allsafe_api.managed_access.service import SESSION_SECONDS, audit, finish, owner_valid, validate
from allsafe_api.models import UserSession, utc_now
from allsafe_api.security import CSRF_COOKIE, SESSION_COOKIE, hash_token, normalized_origin

LOGGER = logging.getLogger(__name__)
MAX_TEXT_BYTES = 50 * 1024  # JSON escaping can expand an 8192-byte input sixfold.
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_SESSIONS = 16
IO_TIMEOUT = 3
ACK_TIMEOUT = 10


class ProtocolError(Exception):
    pass


class SessionEnded(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def parse_message(text: str) -> dict[str, Any]:
    try:
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ProtocolError
        value = json.loads(text, object_pairs_hook=no_duplicates)
        if not isinstance(value, dict):
            raise ProtocolError
        return value
    except (ValueError, UnicodeError, RecursionError, ConfigurationError):
        raise ProtocolError from None


@dataclass
class Connection:
    id: str
    websocket: WebSocket
    verifier: str
    profile: ResolvedProfile
    cols: int
    rows: int
    ssh: asyncssh.SSHClientConnection | None = None
    process: asyncssh.SSHClientProcess[str] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: bool = False
    output_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ack: asyncio.Event = field(default_factory=asyncio.Event)
    sequence: int = 0
    awaiting_ack: bool = False

    async def send(self, message: dict[str, str | int]) -> None:
        async with asyncio.timeout(IO_TIMEOUT):
            async with self.lock:
                await self.websocket.send_json(message)


async def open_ssh(connection: Connection) -> None:
    resolved = connection.profile
    profile = resolved.profile
    assert profile.ssh is not None and resolved.key is not None and resolved.known_hosts is not None
    # In-memory keys/host keys avoid configuration-file races and all implicit
    # .ssh/config, ssh-agent, environment identities and password fallbacks.
    key = asyncssh.import_private_key(resolved.key)
    hosts = asyncssh.import_known_hosts(resolved.known_hosts.decode("utf-8"))
    connection.ssh = await asyncssh.connect(
        profile.host,
        port=profile.ssh.port,
        username=profile.ssh.username,
        client_keys=[key],
        client_certs=[],
        known_hosts=hosts,
        config=None,
        proxy_command=None,
        agent_path=None,
        agent_forwarding=False,
        preferred_auth="publickey",
        password_auth=False,
        kbdint_auth=False,
        gss_auth=False,
        gss_kex=False,
        host_based_auth=False,
        x509_trusted_certs=[],
        x509_trusted_cert_paths=[],
        disable_trivial_auth=True,
        connect_timeout=10,
        login_timeout=10,
        keepalive_interval=15,
        keepalive_count_max=2,
    )
    connection.process = await connection.ssh.create_process(
        request_pty=True,
        term_type="xterm-256color",
        term_size=(connection.cols, connection.rows),
        env={},
        send_env=[],
        encoding="utf-8",
        errors="replace",
        x11_forwarding=False,
        window=64 * 1024,
        max_pktsize=16 * 1024,
    )


class TerminalRelay:
    def __init__(self, session_factory: Any, config_file: str | None) -> None:
        self.session_factory = session_factory
        self.config_file = config_file
        self.connections: dict[str, Connection] = {}
        self.join_lock = asyncio.Lock()

    def identity(self, websocket: WebSocket, session_id: str, csrf: str | None) -> str | None:
        token = websocket.cookies.get(SESSION_COOKIE, "")
        cookie_csrf = websocket.cookies.get(CSRF_COOKIE, "")
        if not 32 <= len(token) <= 128:
            return None
        if csrf is not None and (
            not cookie_csrf or not hmac.compare_digest(hash_token(csrf), hash_token(cookie_csrf))
        ):
            return None
        with self.session_factory() as database:
            terminal = database.get(TerminalSession, session_id)
            if terminal is None or not owner_valid(database, terminal, hash_token(token)):
                return None
            login = database.get(UserSession, terminal.requester_session_id)
            if csrf is not None and (
                login is None or not hmac.compare_digest(login.csrf_hash, hash_token(csrf))
            ):
                return None
        return hash_token(token)

    def claim(self, session_id: str, verifier: str) -> tuple[ResolvedProfile, int, int] | None:
        with self.session_factory.begin() as database:
            terminal = database.get(TerminalSession, session_id)
            if terminal is None or not validate(database, terminal, verifier):
                return None
            if terminal.status != "pending":
                return None
            profile = resolve_profile(self.config_file, terminal.device_id)
            if profile is None or profile.fingerprint != terminal.profile_fingerprint:
                finish(database, terminal, "configuration_changed")
                return None
            changed = database.execute(
                update(TerminalSession)
                .where(TerminalSession.id == session_id, TerminalSession.status == "pending")
                .values(status="connecting")
                .returning(TerminalSession.id)
            ).scalar_one_or_none()
            return (profile, terminal.cols, terminal.rows) if changed else None

    def check(self, connection: Connection) -> bool:
        with self.session_factory.begin() as database:
            terminal = database.get(TerminalSession, connection.id)
            if terminal is None or not validate(database, terminal, connection.verifier):
                return False
            profile = resolve_profile(self.config_file, terminal.device_id)
            if profile is None or profile.fingerprint != terminal.profile_fingerprint:
                finish(database, terminal, "configuration_changed")
                return False
            return True

    def activate(self, connection: Connection) -> bool:
        if not self.check(connection):
            return False
        with self.session_factory.begin() as database:
            terminal = database.get(TerminalSession, connection.id)
            if terminal is None or not validate(database, terminal, connection.verifier):
                return False
            changed = database.execute(
                update(TerminalSession)
                .where(TerminalSession.id == terminal.id, TerminalSession.status == "connecting")
                .values(status="active", expires_at=utc_now() + timedelta(seconds=SESSION_SECONDS))
                .returning(TerminalSession.id)
            ).scalar_one_or_none()
            if changed:
                audit(database, terminal, "started")
            return changed is not None

    def finish_sql(self, session_id: str, reason: str) -> None:
        with self.session_factory.begin() as database:
            terminal = database.get(TerminalSession, session_id)
            if terminal:
                finish(database, terminal, reason)

    async def terminate(self, connection: Connection, reason: str) -> None:
        if connection.closed:
            return
        connection.closed = True
        self.connections.pop(connection.id, None)
        if connection.process:
            connection.process.close()
        if connection.ssh:
            connection.ssh.close()
            try:
                async with asyncio.timeout(IO_TIMEOUT):
                    await connection.ssh.wait_closed()
            except (TimeoutError, OSError, asyncssh.Error):
                connection.ssh.abort()
        try:
            await asyncio.to_thread(self.finish_sql, connection.id, reason)
        except SQLAlchemyError:
            LOGGER.warning("Managed terminal persistence unavailable; transport closed")
        with suppress(Exception):
            await connection.send({"type": "closed", "reason": reason})
        with suppress(Exception):
            async with asyncio.timeout(IO_TIMEOUT):
                await connection.websocket.close(code=1000)

    async def monitor(self, connection: Connection) -> None:
        while True:
            await asyncio.sleep(1)
            if not await asyncio.to_thread(self.check, connection):
                raise SessionEnded("session_unavailable")

    async def receive(self, connection: Connection) -> None:
        window: deque[float] = deque()
        total = 0
        while True:
            message = await connection.websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise SessionEnded("operator_disconnected")
            if message.get("bytes") is not None:
                raise ProtocolError
            event = INPUT_ADAPTER.validate_python(parse_message(message.get("text") or ""))
            now = time.monotonic()
            while window and window[0] <= now - 1:
                window.popleft()
            if len(window) >= 100:
                raise ProtocolError
            window.append(now)
            if not await asyncio.to_thread(self.check, connection):
                raise SessionEnded("session_unavailable")
            if connection.process is None:
                raise ProtocolError
            if isinstance(event, Input):
                total += len(event.data.encode("utf-8"))
                if total > MAX_INPUT_BYTES:
                    raise ProtocolError
                async with asyncio.timeout(IO_TIMEOUT):
                    connection.process.stdin.write(event.data)
                    await connection.process.stdin.drain()
            elif isinstance(event, Ack):
                if not connection.awaiting_ack or event.sequence != connection.sequence:
                    raise ProtocolError
                connection.awaiting_ack = False
                connection.ack.set()
            else:
                connection.process.change_terminal_size(event.cols, event.rows)

    async def output(self, connection: Connection, stream: asyncssh.SSHReader[str]) -> None:
        while True:
            # 4096 Unicode scalar values occupy at most 16 KiB UTF-8.
            data = await stream.read(4096)
            if not data:
                return
            async with connection.output_lock:
                connection.sequence += 1
                connection.ack.clear()
                connection.awaiting_ack = True
                await connection.send(
                    {
                        "type": "output",
                        "data": data,
                        "sequence": connection.sequence,
                    }
                )
                async with asyncio.timeout(ACK_TIMEOUT):
                    await connection.ack.wait()

    async def session(self, connection: Connection) -> None:
        async with asyncio.timeout(10):
            await open_ssh(connection)
        if not await asyncio.to_thread(self.activate, connection):
            raise SessionEnded("session_unavailable")
        await connection.send({"type": "ready"})
        assert connection.process is not None
        receive_task = asyncio.create_task(self.receive(connection))
        output_tasks = [
            asyncio.create_task(self.output(connection, connection.process.stdout)),
            asyncio.create_task(self.output(connection, connection.process.stderr)),
        ]
        tasks = [*output_tasks, receive_task]
        try:
            # stdout/stderr may close independently; only process exit or browser
            # disconnect should terminate an otherwise healthy interactive shell.
            exit_task = asyncio.create_task(connection.process.wait_closed())
            tasks.append(exit_task)
            while tasks:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                    if task is receive_task:
                        raise SessionEnded("ssh_closed")
                    if task is exit_task:
                        # SSH process exit may arrive before the browser has
                        # consumed the final bounded output chunk. Drain both
                        # streams, including their ACK, before closing transport.
                        async with asyncio.timeout(ACK_TIMEOUT + IO_TIMEOUT):
                            await asyncio.gather(*output_tasks)
                        raise SessionEnded("ssh_closed")
                tasks = [task for task in tasks if task not in done]
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, connection: Connection) -> None:
        tasks = [
            asyncio.create_task(self.session(connection)),
            asyncio.create_task(self.monitor(connection)),
        ]
        reason = "ssh_closed"
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except SessionEnded as error:
            reason = error.reason
        except (ProtocolError, ValidationError):
            reason = "protocol_violation"
        except SQLAlchemyError:
            reason = "state_unavailable"
        except ConfigurationError:
            reason = "configuration_unavailable"
        except (
            TimeoutError,
            OSError,
            asyncssh.Error,
            ValueError,
            RuntimeError,
            WebSocketDisconnect,
        ):
            reason = "connection_failed"
        except asyncio.CancelledError:
            reason = "transport_closed"
        finally:
            with anyio.CancelScope(shield=True):
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await self.terminate(connection, reason)

    async def shutdown(self) -> None:
        for connection in list(self.connections.values()):
            await self.terminate(connection, "server_shutdown")


async def connect(websocket: WebSocket, session_id: str) -> None:
    configured = websocket.app.state.settings
    trusted = {normalized_origin(configured.frontend_url), normalized_origin(configured.api_url)}
    if (
        websocket.headers.get("origin", "").lower() not in trusted
        or websocket.headers.get("sec-fetch-site") == "cross-site"
        or websocket.headers.get("authorization")
        or websocket.url.query
    ):
        await websocket.close(code=1008)
        return
    relay: TerminalRelay = websocket.app.state.terminal_relay
    try:
        if not await asyncio.to_thread(relay.identity, websocket, session_id, None):
            await websocket.close(code=1008)
            return
    except SQLAlchemyError:
        await websocket.close(code=1011)
        return
    await websocket.accept()
    connection: Connection | None = None
    try:
        async with asyncio.timeout(5):
            message = await websocket.receive()
        if message.get("bytes") is not None or message["type"] != "websocket.receive":
            raise ProtocolError
        hello = Hello.model_validate(parse_message(message.get("text") or ""))
        verifier = await asyncio.to_thread(relay.identity, websocket, session_id, hello.csrf)
        if verifier is None:
            raise ProtocolError
        async with relay.join_lock:
            if len(relay.connections) >= MAX_SESSIONS:
                raise ProtocolError
            claimed = await asyncio.to_thread(relay.claim, session_id, verifier)
            if claimed is None:
                raise ProtocolError
            profile, cols, rows = claimed
            connection = Connection(session_id, websocket, verifier, profile, cols, rows)
            relay.connections[session_id] = connection
        await relay.run(connection)
    except (
        ProtocolError,
        ValidationError,
        TimeoutError,
        WebSocketDisconnect,
        SQLAlchemyError,
        ConfigurationError,
        asyncio.CancelledError,
    ):
        with anyio.CancelScope(shield=True):
            if connection:
                await relay.terminate(connection, "handshake_closed")
            with suppress(Exception):
                await websocket.close(code=1008)
