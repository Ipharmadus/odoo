#!/usr/bin/env python3

import socket
import ssl
import time
import xmlrpc.client


class OdooXmlRpcClient:
    def __init__(
        self, url, db, username, password, verify_ssl=True, retries=4, retry_delay=2.0
    ):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.retries = max(1, int(retries))
        self.retry_delay = float(retry_delay)
        transport = None
        if self.url.startswith("https://") and not verify_ssl:
            ssl_context = ssl._create_unverified_context()
            transport = xmlrpc.client.SafeTransport(context=ssl_context)
        self.common = xmlrpc.client.ServerProxy(
            "{}/xmlrpc/2/common".format(self.url),
            transport=transport,
        )
        self.models = xmlrpc.client.ServerProxy(
            "{}/xmlrpc/2/object".format(self.url),
            transport=transport,
        )
        self.uid = self.common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise RuntimeError(
                "Authentication failed for {} on database {}".format(
                    self.username, self.db
                )
            )

    def execute(self, model, method, *args, **kwargs):
        # Reintenta solo fallos de transporte (502/504, cortes de conexion...).
        # Los Fault son errores de aplicacion y se propagan sin reintentar.
        last_error = None
        for attempt in range(self.retries):
            try:
                return self.models.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    model,
                    method,
                    list(args),
                    kwargs,
                )
            except (xmlrpc.client.ProtocolError, OSError, socket.timeout) as error:
                last_error = error
                if attempt + 1 >= self.retries:
                    break
                time.sleep(self.retry_delay * (attempt + 1))
        raise last_error

    def search(self, model, domain, **kwargs):
        return self.execute(model, "search", domain, **kwargs)

    def read(self, model, ids, fields=None, **kwargs):
        read_kwargs = dict(kwargs)
        if fields is not None:
            read_kwargs["fields"] = fields
        return self.execute(model, "read", ids, **read_kwargs)

    def search_read(self, model, domain, fields=None, **kwargs):
        read_kwargs = dict(kwargs)
        if fields is not None:
            read_kwargs["fields"] = fields
        return self.execute(model, "search_read", domain, **read_kwargs)

    def write(self, model, ids, values):
        return self.execute(model, "write", ids, values)
