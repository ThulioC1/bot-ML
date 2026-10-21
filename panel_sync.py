# -*- coding: utf-8 -*-
"""Ponte do bot com o painel (Firebase Auth + Firestore), só com requests.

O bot roda atrás de CGNAT (Kali/Termux), então o painel nunca fala com ele
diretamente: o painel escreve no Firestore e o bot lê por HTTPS de saída.

Coleções (todas de nível raiz):
  panel_control/state    -> painel escreve {flags}; bot lê
  panel_status/state     -> bot escreve status/vitrine/logs; painel lê
  panel_commands/{id}    -> painel cria {type, payload, status:"pending"};
                            bot processa e marca done/error
"""

import os
import threading
import time

import requests

FIRESTORE_BASE = ("https://firestore.googleapis.com/v1/projects/{project}"
                  "/databases/(default)/documents")
IDENTITY_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
TOKEN_URL = "https://securetoken.googleapis.com/v1/token"


def _to_value(value):
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {str(k): _to_value(v) for k, v in value.items()}}}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_to_value(v) for v in value]}}
    if value is None:
        return {"nullValue": None}
    return {"stringValue": str(value)}


def _from_value(value):
    if not isinstance(value, dict):
        return None
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "stringValue" in value:
        return value["stringValue"]
    if "timestampValue" in value:
        return value["timestampValue"]
    if "mapValue" in value:
        return _from_fields((value.get("mapValue") or {}).get("fields") or {})
    if "arrayValue" in value:
        values = (value.get("arrayValue") or {}).get("values") or []
        return [_from_value(v) for v in values]
    return None


def _from_fields(fields):
    return {key: _from_value(val) for key, val in (fields or {}).items()}


def _from_doc(doc):
    return _from_fields((doc or {}).get("fields") or {})


class FirebaseAuth:
    def __init__(self, api_key, email, password):
        self.api_key = api_key
        self.email = email
        self.password = password
        self.token = ""
        self.refresh_token = ""
        self.expires_at = 0.0
        self.uid = ""

    def _store(self, data):
        self.token = data.get("idToken") or data.get("access_token") or ""
        self.refresh_token = (data.get("refreshToken")
                              or data.get("refresh_token")
                              or self.refresh_token)
        self.uid = data.get("localId") or data.get("user_id") or self.uid
        expires_in = data.get("expiresIn") or data.get("expires_in") or "3600"
        self.expires_at = time.time() + max(60, int(expires_in) - 120)

    def sign_in(self):
        resp = requests.post(IDENTITY_URL, params={"key": self.api_key},
                             json={"email": self.email, "password": self.password,
                                   "returnSecureToken": True}, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"login Firebase falhou ({resp.status_code}): {resp.text[:200]}")
        self._store(resp.json())

    def refresh(self):
        resp = requests.post(TOKEN_URL, params={"key": self.api_key},
                             data={"grant_type": "refresh_token",
                                   "refresh_token": self.refresh_token}, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"refresh Firebase falhou ({resp.status_code}): {resp.text[:200]}")
        self._store(resp.json())

    def bearer(self):
        if not self.token:
            self.sign_in()
        elif time.time() >= self.expires_at:
            try:
                self.refresh()
            except Exception:
                self.sign_in()
        return self.token


class PanelSync:
    def __init__(self, on_flags, on_command, status, log):
        self.on_flags = on_flags
        self.on_command = on_command
        self.status = status
        self.log = log
        self.project = (os.getenv("FIREBASE_PROJECT_ID") or "").strip()
        self.api_key = (os.getenv("FIREBASE_API_KEY") or "").strip()
        self.email = (os.getenv("FIREBASE_BOT_EMAIL") or "").strip()
        self.password = os.getenv("FIREBASE_BOT_PASSWORD") or ""
        try:
            self.interval = max(3, int(os.getenv("PANEL_POLL_SECONDS", "10")))
        except ValueError:
            self.interval = 10
        self.auth = FirebaseAuth(self.api_key, self.email, self.password)

    @property
    def enabled(self):
        return bool(self.project and self.api_key and self.email and self.password)

    def base_url(self):
        return FIRESTORE_BASE.format(project=self.project)

    def _request(self, method, url, **kwargs):
        last = None
        for attempt in range(2):
            headers = dict(kwargs.get("headers") or {})
            headers["Authorization"] = f"Bearer {self.auth.bearer()}"
            resp = requests.request(method, url, headers=headers, timeout=25,
                                    **{k: v for k, v in kwargs.items() if k != "headers"})
            if resp.status_code == 401 and attempt == 0:
                self.auth.token = ""
                last = resp
                continue
            return resp
        return last

    def get_doc(self, path):
        resp = self._request("GET", f"{self.base_url()}/{path}")
        if resp.status_code == 404:
            return {}
        if resp.status_code != 200:
            raise RuntimeError(f"GET {path}: {resp.status_code} {resp.text[:200]}")
        return _from_doc(resp.json())

    def pending_commands(self):
        query = {
            "structuredQuery": {
                "from": [{"collectionId": "panel_commands"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "status"},
                        "op": "EQUAL",
                        "value": {"stringValue": "pending"},
                    }
                },
                "limit": 10,
            }
        }
        resp = self._request("POST", f"{self.base_url()}:runQuery", json=query)
        if resp.status_code != 200:
            raise RuntimeError(f"runQuery: {resp.status_code} {resp.text[:200]}")
        comandos = []
        for item in resp.json():
            doc = item.get("document") if isinstance(item, dict) else None
            if not doc:
                continue
            doc_id = str(doc.get("name") or "").rsplit("/", 1)[-1]
            comandos.append((doc_id, _from_doc(doc)))
        return comandos

    def update_command(self, doc_id, status, result):
        url = (f"{self.base_url()}/panel_commands/{doc_id}"
               "?updateMask.fieldPaths=status"
               "&updateMask.fieldPaths=result"
               "&updateMask.fieldPaths=processed_at")
        body = {"fields": {
            "status": _to_value(status),
            "result": _to_value(str(result)[:900]),
            "processed_at": _to_value(int(time.time())),
        }}
        resp = self._request("PATCH", url, json=body)
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"PATCH comando {doc_id}: {resp.status_code} {resp.text[:200]}")

    def write_status(self):
        dados = self.status()
        if not isinstance(dados, dict):
            return
        body = {"fields": {str(k): _to_value(v) for k, v in dados.items()}}
        resp = self._request("PATCH", f"{self.base_url()}/panel_status/state", json=body)
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"PATCH status: {resp.status_code} {resp.text[:200]}")

    def run_command(self, doc_id, command):
        kind = str(command.get("type") or "")
        payload = command.get("payload")
        try:
            result = self.on_command(kind, payload)
            self.update_command(doc_id, "done", result)
            self.log(f"🎛️ Painel: comando '{kind}' executado.")
        except Exception as exc:
            self.update_command(doc_id, "error", f"{type(exc).__name__}: {exc}")
            self.log(f"⚠️ Painel: comando '{kind}' falhou: {type(exc).__name__}: {exc}")

    def tick(self):
        control = self.get_doc("panel_control/state")
        flags = control.get("flags") if isinstance(control, dict) else None
        if isinstance(flags, dict) and flags:
            self.on_flags(flags)
        for doc_id, command in self.pending_commands():
            self.run_command(doc_id, command)
        self.write_status()

    def loop(self):
        erros = 0
        ultimo = ""
        while True:
            try:
                self.tick()
                if erros:
                    self.log("✅ Painel: sincronização restabelecida.")
                erros = 0
                ultimo = ""
            except Exception as exc:
                texto = f"{type(exc).__name__}: {exc}"
                erros += 1
                if texto != ultimo or erros % 10 == 1:
                    self.log(f"⚠️ Painel: {texto}")
                    ultimo = texto
                self.auth.token = ""
                time.sleep(min(300, max(30, self.interval) * min(erros, 10)))
                continue
            time.sleep(self.interval)

    def start(self):
        if not self.enabled:
            self.log("ℹ️ Painel: Firebase não configurado — painel desativado.")
            return False
        try:
            self.auth.bearer()
            self.log(f"🔑 Painel: bot autenticado como {self.email} "
                     f"(UID {self.auth.uid or '?'}).")
        except Exception as exc:
            self.log(f"⚠️ Painel: login Firebase falhou ({type(exc).__name__}: "
                     f"{exc}); vou continuar tentando.")
        threading.Thread(target=self.loop, name="panel-sync", daemon=True).start()
        self.log(f"✅ Painel: sincronizando a cada {self.interval}s.")
        return True


def start_panel_sync(on_flags, on_command, status, log):
    return PanelSync(on_flags, on_command, status, log).start()
