"""Bounded, ephemeral one-worker relay. No frame or input logging/persistence."""

import asyncio
import hmac
import json
import logging
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

import anyio
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from allsafe_api.models import Device, UserSession
from allsafe_api.remote_desktop.jpeg import baseline_dimensions
from allsafe_api.remote_desktop.models import DesktopSession
from allsafe_api.remote_desktop.schemas import (
    AGENT_ADAPTER,
    INPUT_ADAPTER,
    AgentHello,
    Display,
    ViewerHello,
)
from allsafe_api.remote_desktop.service import (
    audit,
    device_valid,
    expire,
    finish,
    owner_valid,
)
from allsafe_api.security import CSRF_COOKIE, SESSION_COOKIE, hash_token, normalized_origin

MAX_FRAME_BYTES = 768 * 1024
MAX_TEXT_BYTES = 2048
HELLO_TIMEOUT = 5
SEND_TIMEOUT = 3
PEER_JOIN_TIMEOUT = 60
MAX_RELAYS = 32
LOGGER = logging.getLogger(__name__)


class ProtocolError(Exception):
    pass


def strict_json(value: str) -> dict[str, Any]:
    try:
        if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ProtocolError
    except UnicodeError:
        raise ProtocolError from None

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ProtocolError
            result[key] = item
        return result

    try:
        result = json.loads(
            value,
            object_pairs_hook=object_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError()),
        )
    except (ValueError, RecursionError):
        raise ProtocolError from None
    if not isinstance(result, dict):
        raise ProtocolError
    return result


@dataclass
class Peer:
    websocket: WebSocket
    verifier: str
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, value: dict[str, Any] | bytes) -> None:
        # Waiting for a lock is also bounded; a slow viewer cannot accumulate tasks
        # or block revocation/closure indefinitely.
        async with asyncio.timeout(SEND_TIMEOUT):
            async with self.send_lock:
                if isinstance(value, bytes):
                    await self.websocket.send_bytes(value)
                else:
                    await self.websocket.send_json(value)


@dataclass
class Pair:
    id: str
    viewer: Peer | None = None
    agent: Peer | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False
    display_dimensions: tuple[int, int] | None = None
    frames: deque[float] = field(default_factory=deque)
    inputs: deque[float] = field(default_factory=deque)


class DesktopRelay:
    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory
        self.pairs: dict[str, Pair] = {}
        self.lock = asyncio.Lock()

    def validate(
        self,
        session_id: str,
        *,
        viewer_verifier: str | None = None,
        agent_verifier: str | None = None,
    ) -> tuple[bool, str]:
        with self.session_factory.begin() as database:
            desktop = database.get(DesktopSession, session_id)
            if desktop is None:
                return False, "session_unavailable"
            expire(database, desktop)
            if desktop.status not in {"approved", "active"}:
                return False, "session_unavailable"
            if not owner_valid(database, desktop):
                finish(database, desktop, "operator_unavailable")
                return False, "operator_unavailable"
            if viewer_verifier is not None:
                login = database.get(UserSession, desktop.requester_session_id)
                if login is None or not hmac.compare_digest(login.token_hash, viewer_verifier):
                    return False, "operator_unavailable"
            device = database.get(Device, desktop.device_id)
            if device is None or device.revoked_at is not None:
                finish(database, desktop, "device_unavailable")
                return False, "device_unavailable"
            if agent_verifier is not None and not device_valid(device, agent_verifier):
                finish(database, desktop, "device_credentials_changed")
                return False, "device_credentials_changed"
            return True, desktop.mode

    def activate(self, session_id: str) -> bool:
        with self.session_factory.begin() as database:
            desktop = database.get(DesktopSession, session_id)
            if desktop is None:
                return False
            expire(database, desktop)
            if desktop.status != "approved" or not owner_valid(database, desktop):
                return False
            changed = database.execute(
                update(DesktopSession)
                .where(DesktopSession.id == session_id, DesktopSession.status == "approved")
                .values(status="active")
                .returning(DesktopSession.id)
            ).scalar_one_or_none()
            if changed:
                database.refresh(desktop)
                audit(database, desktop, "started")
            return changed is not None

    async def join(self, session_id: str, peer: Peer, *, agent: bool) -> Pair | None:
        start = False
        async with self.lock:
            pair = self.pairs.get(session_id)
            if pair is None:
                if len(self.pairs) >= MAX_RELAYS:
                    return None
                pair = Pair(id=session_id)
                self.pairs[session_id] = pair
            if pair.closed or (pair.agent if agent else pair.viewer) is not None:
                return None
            if agent:
                pair.agent = peer
            else:
                pair.viewer = peer
            if pair.viewer is not None and pair.agent is not None:
                start = True
        # Never hold the global registry lock across database work or network I/O.
        # A stalled room must not delay consent/revocation in unrelated rooms.
        if start:
            try:
                if not await asyncio.to_thread(self.activate, session_id) or pair.closed:
                    await self.terminate(pair, "session_unavailable")
                else:
                    pair.ready.set()
                    assert pair.viewer is not None and pair.agent is not None
                    await pair.viewer.send({"type": "ready"})
                    await pair.agent.send({"type": "ready"})
            except (TimeoutError, RuntimeError, WebSocketDisconnect):
                await self.terminate(pair, "transport_closed")
            except SQLAlchemyError:
                await self.terminate(pair, "state_unavailable")
            except asyncio.CancelledError:
                with anyio.CancelScope(shield=True):
                    await self.terminate(pair, "transport_closed")
                raise
        return pair

    def finish_sql(self, session_id: str, reason: str) -> None:
        with self.session_factory.begin() as database:
            desktop = database.get(DesktopSession, session_id)
            if desktop:
                expire(database, desktop)
                finish(database, desktop, reason)

    async def terminate(self, pair: Pair, reason: str) -> None:
        async with self.lock:
            if self.pairs.get(pair.id) is not pair:
                return
            pair.closed = True
            pair.ready.set()
            self.pairs.pop(pair.id, None)
        # ASGI cancellation during disconnect must not abandon SQL termination or
        # leave the other endpoint controlling a granted desktop.
        with anyio.CancelScope(shield=True):
            try:
                await asyncio.to_thread(self.finish_sql, pair.id, reason)
            except SQLAlchemyError:
                # Transport closure must succeed even when the audit database is
                # unavailable. Do not log frames, input or SQL exception values.
                LOGGER.warning("Desktop state persistence unavailable; relay closed")
            for peer in (pair.agent, pair.viewer):
                if peer:
                    with suppress(Exception):
                        await peer.send({"type": "closed", "reason": reason})
                    with suppress(Exception):
                        async with asyncio.timeout(SEND_TIMEOUT):
                            await peer.websocket.close(code=1000)

    async def check_pair(self, pair: Pair) -> tuple[bool, str]:
        if pair.closed:
            return False, "session_unavailable"
        return await asyncio.to_thread(
            self.validate,
            pair.id,
            viewer_verifier=pair.viewer.verifier if pair.viewer else None,
            agent_verifier=pair.agent.verifier if pair.agent else None,
        )

    async def monitor(self, pair: Pair) -> None:
        joined_at = time.monotonic()
        while not pair.closed:
            await asyncio.sleep(1)
            valid, reason = await self.check_pair(pair)
            if not valid:
                await self.terminate(pair, reason)
                return
            if not pair.ready.is_set() and time.monotonic() - joined_at > PEER_JOIN_TIMEOUT:
                await self.terminate(pair, "peer_join_timeout")
                return

    async def receive(self, pair: Pair, peer: Peer, *, agent: bool) -> None:
        # Waiting for the second peer must still observe disconnect and never
        # accept pre-ready frame/input buffering.
        while not pair.closed:
            message = await peer.websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if pair.closed:
                return
            if agent and message.get("text"):
                event = AGENT_ADAPTER.validate_python(strict_json(message["text"]))
                if not isinstance(event, Display):
                    await self.terminate(pair, "local_user_stopped")
                    return
            if not pair.ready.is_set():
                raise ProtocolError
            valid, mode = await self.check_pair(pair)
            if not valid:
                await self.terminate(pair, mode)
                return
            if agent:
                destination = pair.viewer
                binary = message.get("bytes")
                if binary is not None:
                    if (
                        pair.display_dimensions is None
                        or len(binary) > MAX_FRAME_BYTES
                        or baseline_dimensions(binary) != pair.display_dimensions
                    ):
                        raise ProtocolError
                    rate_limit(pair.frames, 5)
                    assert destination is not None
                    await destination.send(binary)
                else:
                    event = AGENT_ADAPTER.validate_python(strict_json(message.get("text") or ""))
                    if isinstance(event, Display):
                        if pair.display_dimensions is not None:
                            # A fixed primary-display size for the entire grant.
                            raise ProtocolError
                        pair.display_dimensions = (event.width, event.height)
                        assert destination is not None
                        await destination.send(event.model_dump())
                    else:
                        await self.terminate(pair, "local_user_stopped")
                        return
            else:
                if message.get("bytes") is not None:
                    raise ProtocolError
                event = INPUT_ADAPTER.validate_python(strict_json(message.get("text") or ""))
                rate_limit(pair.inputs, 100)
                if mode != "control":
                    raise ProtocolError
                assert pair.agent is not None
                await pair.agent.send(event.model_dump())

    async def run(self, pair: Pair, peer: Peer, *, agent: bool) -> None:
        receive = asyncio.create_task(self.receive(pair, peer, agent=agent))
        monitor = asyncio.create_task(self.monitor(pair))
        reason = "peer_disconnected"
        try:
            done, _ = await asyncio.wait((receive, monitor), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ProtocolError, ValidationError):
            reason = "protocol_violation"
        except (TimeoutError, WebSocketDisconnect, RuntimeError, OSError):
            reason = "transport_closed"
        except SQLAlchemyError:
            reason = "state_unavailable"
        except asyncio.CancelledError:
            reason = "transport_closed"
        finally:
            with anyio.CancelScope(shield=True):
                receive.cancel()
                monitor.cancel()
                await asyncio.gather(receive, monitor, return_exceptions=True)
                await self.terminate(pair, reason)

    async def shutdown(self) -> None:
        for pair in list(self.pairs.values()):
            await self.terminate(pair, "server_shutdown")


def rate_limit(window: deque[float], maximum: int) -> None:
    now = time.monotonic()
    while window and window[0] <= now - 1:
        window.popleft()
    if len(window) >= maximum:
        raise ProtocolError
    window.append(now)


async def hello(websocket: WebSocket) -> dict[str, Any]:
    async with asyncio.timeout(HELLO_TIMEOUT):
        message = await websocket.receive()
    if message["type"] != "websocket.receive" or message.get("bytes") is not None:
        raise ProtocolError
    return strict_json(message.get("text") or "")


def viewer_identity(websocket: WebSocket, session_id: str, csrf: str | None) -> str | None:
    token = websocket.cookies.get(SESSION_COOKIE, "")
    cookie_csrf = websocket.cookies.get(CSRF_COOKIE, "")
    if not 32 <= len(token) <= 128:
        return None
    if csrf is not None and (
        not cookie_csrf or not hmac.compare_digest(hash_token(csrf), hash_token(cookie_csrf))
    ):
        return None
    with websocket.app.state.session_factory() as database:
        desktop = database.get(DesktopSession, session_id)
        if (
            desktop is None
            or desktop.status not in {"approved", "active"}
            or not owner_valid(database, desktop)
        ):
            return None
        login = database.get(UserSession, desktop.requester_session_id)
        if (
            login is None
            or not hmac.compare_digest(login.token_hash, hash_token(token))
            or (csrf is not None and not hmac.compare_digest(login.csrf_hash, hash_token(csrf)))
        ):
            return None
    return hash_token(token)


async def connect_viewer(websocket: WebSocket, session_id: str) -> None:
    configured = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    trusted = {normalized_origin(configured.frontend_url), normalized_origin(configured.api_url)}
    if (
        origin is None
        or origin.lower() not in trusted
        or websocket.headers.get("sec-fetch-site") == "cross-site"
        or websocket.headers.get("authorization")
        or websocket.url.query
    ):
        await websocket.close(code=1008)
        return
    if not await asyncio.to_thread(viewer_identity, websocket, session_id, None):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    relay: DesktopRelay = websocket.app.state.desktop_relay
    pair: Pair | None = None
    try:
        message = ViewerHello.model_validate(await hello(websocket))
        verifier = await asyncio.to_thread(viewer_identity, websocket, session_id, message.csrf)
        if verifier is None:
            raise ProtocolError
        valid, _ = await asyncio.to_thread(relay.validate, session_id, viewer_verifier=verifier)
        if not valid:
            raise ProtocolError
        peer = Peer(websocket, verifier)
        pair = await relay.join(session_id, peer, agent=False)
        if pair is None:
            raise ProtocolError
        await relay.run(pair, peer, agent=False)
    except (
        ProtocolError,
        ValidationError,
        TimeoutError,
        WebSocketDisconnect,
        RuntimeError,
        asyncio.CancelledError,
    ):
        await failed_handshake(relay, websocket, session_id, pair)


async def connect_agent(websocket: WebSocket, session_id: str) -> None:
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if (
        websocket.headers.get("origin") is not None
        or websocket.url.query
        or scheme.lower() != "bearer"
        or not 32 <= len(token) <= 128
    ):
        await websocket.close(code=1008)
        return
    supplied_hash = hash_token(token)

    def preflight() -> bool:
        with websocket.app.state.session_factory() as database:
            desktop = database.get(DesktopSession, session_id)
            if desktop is None or desktop.status not in {"approved", "active"}:
                return False
            device = database.get(Device, desktop.device_id)
            return device_valid(device, supplied_hash) and owner_valid(database, desktop)

    if not await asyncio.to_thread(preflight):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    relay: DesktopRelay = websocket.app.state.desktop_relay
    pair: Pair | None = None
    try:
        message = AgentHello.model_validate(await hello(websocket))

        def authenticate_device() -> bool:
            with websocket.app.state.session_factory() as database:
                desktop = database.get(DesktopSession, session_id)
                device = database.get(Device, message.device_id)
                return bool(
                    desktop
                    and desktop.device_id == message.device_id
                    and device_valid(device, supplied_hash)
                )

        if not await asyncio.to_thread(authenticate_device):
            raise ProtocolError
        valid, _ = await asyncio.to_thread(relay.validate, session_id, agent_verifier=supplied_hash)
        if not valid:
            raise ProtocolError
        peer = Peer(websocket, supplied_hash)
        pair = await relay.join(session_id, peer, agent=True)
        if pair is None:
            raise ProtocolError
        await relay.run(pair, peer, agent=True)
    except (
        ProtocolError,
        ValidationError,
        TimeoutError,
        WebSocketDisconnect,
        RuntimeError,
        asyncio.CancelledError,
    ):
        await failed_handshake(relay, websocket, session_id, pair)


async def failed_handshake(
    relay: DesktopRelay, websocket: WebSocket, session_id: str, pair: Pair | None
) -> None:
    with anyio.CancelScope(shield=True):
        if pair:
            await relay.terminate(pair, "transport_closed")
        else:
            async with relay.lock:
                unpaired = session_id not in relay.pairs
            # A failed duplicate must not terminate the original active pair.
            # A legitimate first endpoint that disconnects before joining must
            # not leave its consent grant reusable after the connection attempt.
            if unpaired:
                with suppress(SQLAlchemyError):
                    await asyncio.to_thread(relay.finish_sql, session_id, "handshake_closed")
        with suppress(Exception):
            async with asyncio.timeout(SEND_TIMEOUT):
                await websocket.close(code=1008)
