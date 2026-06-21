"""Windows-only asyncio shims for the Synapse daemon.

Python 3.12's Proactor event loop can stop accepting new TCP connections after
AcceptEx raises WinError 64 / ERROR_NETNAME_DELETED for one dropped client.
That leaves existing sockets alive but silently kills fresh LAN/WAN connects,
which is exactly the failure mode that makes phone pairing / Cloudtap handoff
look flaky even though the daemon process itself never exits.

Upstream CPython is addressing this in the Proactor server path. Until that
lands in the interpreter we're running, we patch the accept loop locally so a
single reset connection is treated as noise rather than a fatal server-socket
error.
"""

from __future__ import annotations

import sys


def install_accept_reset_workaround() -> bool:
    """Keep the Windows Proactor accept loop alive after WinError 64 resets.

    Returns ``True`` when a patch was installed for this interpreter session.
    Returns ``False`` on non-Windows platforms or if the patch was already
    active.
    """

    if sys.platform != "win32":
        return False

    import asyncio.proactor_events as proactor_events
    import asyncio.windows_events as windows_events

    if getattr(windows_events.IocpProactor.accept, "_synapse_patched", False):
        return False

    reset_codes = {
        windows_events._overlapped.ERROR_NETNAME_DELETED,
        windows_events._overlapped.ERROR_OPERATION_ABORTED,
    }
    original_start_serving = proactor_events.BaseProactorEventLoop._start_serving

    def patched_accept(self, listener):
        self._register_with_iocp(listener)
        conn = self._get_accept_socket(listener.family)
        ov = windows_events._overlapped.Overlapped(windows_events.NULL)
        ov.AcceptEx(listener.fileno(), conn.fileno())

        def finish_accept(trans, key, ov):
            try:
                ov.getresult()
            except OSError as exc:
                if exc.winerror in reset_codes:
                    raise ConnectionResetError(*exc.args)
                raise
            buf = windows_events.struct.pack("@P", listener.fileno())
            conn.setsockopt(
                windows_events.socket.SOL_SOCKET,
                windows_events._overlapped.SO_UPDATE_ACCEPT_CONTEXT,
                buf,
            )
            conn.settimeout(listener.gettimeout())
            return conn, conn.getpeername()

        async def accept_coro(future, accept_socket):
            try:
                await future
            except windows_events.exceptions.CancelledError:
                accept_socket.close()
                raise
            except ConnectionResetError:
                accept_socket.close()

        future = self._register(ov, listener, finish_accept)
        coro = accept_coro(future, conn)
        windows_events.tasks.ensure_future(coro, loop=self._loop)
        return future

    def patched_start_serving(
        self,
        protocol_factory,
        sock,
        sslcontext=None,
        server=None,
        backlog=100,
        ssl_handshake_timeout=None,
        ssl_shutdown_timeout=None,
    ):
        def loop(f=None):
            try:
                if f is not None:
                    conn, addr = f.result()
                    if self._debug:
                        proactor_events.logger.debug(
                            "%r got a new connection from %r: %r",
                            server,
                            addr,
                            conn,
                        )
                    protocol = protocol_factory()
                    if sslcontext is not None:
                        self._make_ssl_transport(
                            conn,
                            protocol,
                            sslcontext,
                            server_side=True,
                            extra={"peername": addr},
                            server=server,
                            ssl_handshake_timeout=ssl_handshake_timeout,
                            ssl_shutdown_timeout=ssl_shutdown_timeout,
                        )
                    else:
                        self._make_socket_transport(
                            conn,
                            protocol,
                            extra={"peername": addr},
                            server=server,
                        )
                if self.is_closed():
                    return
                f = self._proactor.accept(sock)
            except ConnectionResetError:
                if self.is_closed():
                    return
                f = self._proactor.accept(sock)
            except OSError as exc:
                if sock.fileno() != -1:
                    self.call_exception_handler(
                        {
                            "message": "Accept failed on a socket",
                            "exception": exc,
                            "socket": proactor_events.trsock.TransportSocket(sock),
                        }
                    )
                    sock.close()
                elif self._debug:
                    proactor_events.logger.debug(
                        "Accept failed on socket %r", sock, exc_info=True
                    )
                return
            except proactor_events.exceptions.CancelledError:
                sock.close()
                return

            self._accept_futures[sock.fileno()] = f
            f.add_done_callback(loop)

        self.call_soon(loop)

    patched_accept._synapse_patched = True  # type: ignore[attr-defined]
    patched_start_serving._synapse_patched = True  # type: ignore[attr-defined]

    windows_events.IocpProactor.accept = patched_accept
    proactor_events.BaseProactorEventLoop._start_serving = patched_start_serving
    proactor_events.BaseProactorEventLoop._synapse_original_start_serving = (
        original_start_serving  # type: ignore[attr-defined]
    )
    return True
