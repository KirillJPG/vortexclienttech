import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Tuple
from .database import authenticate, verify_license, check_hwid_subscription, verify_hwid_subscription
from .crypto import encrypt_payload, decrypt_payload
from .config import SERVER_SECRET, CHEATS_DIR

app = FastAPI(
    title="Auth API Server",
    description="Backend verification server for C++ Loader with AES-256 Encryption & File Delivery",
    version="1.2.0"
)


class RawAuthRequest(BaseModel):
    data: Optional[str] = Field(None, description="Зашифрованный полезный груз (Hex-строка)")
    key: Optional[str] = Field(None, description="Открытый ключ (для отладки)")
    hwid: Optional[str] = Field(None, description="Открытый HWID (для отладки)")
    filename: Optional[str] = Field(None, description="Имя запрашиваемого файла чита")


def extract_payload(req: RawAuthRequest) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Извлекает полезную нагрузку из зашифрованного или открытого запроса"""
    if req.data:
        decrypted_json_str = decrypt_payload(req.data, password=SERVER_SECRET)
        if not decrypted_json_str:
            return True, None
        try:
            return True, json.loads(decrypted_json_str)
        except Exception:
            return True, None
    else:
        return False, {
            "key": req.key or "",
            "hwid": req.hwid or "",
            "filename": req.filename or ""
        }


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "loader-auth-api"}


@app.post("/api/v1/auth")
async def api_auth(req: RawAuthRequest, request: Request):
    """
    Эндпоинт проверки лицензии/подписки.
    - Если передан только HWID (из чита): проверяет наличие активных подписок для этого устройства.
    - Если передан ключ (из лоадера): регистрирует/активирует ключ и привязывает HWID.
    Поддерживает сквозное шифрование AES-256-CBC с PBKDF2.
    """
    client_ip = request.client.host if (request and getattr(request, "client", None) and request.client) else "unknown"
    is_encrypted, payload = extract_payload(req)

    if payload is None:
        err_dict = {"status": "error", "message": "DECRYPTION_FAILED"}
        return {"data": encrypt_payload(json.dumps(err_dict), password=SERVER_SECRET)}

    key = (payload.get("key") or "").strip()
    hwid = (payload.get("hwid") or "").strip()

    if not key and hwid:
        # Проверка по HWID без ключа (для чита)
        success, message, data = await check_hwid_subscription(
            hwid=hwid,
            ip=client_ip
        )
    else:
        # Проверка лицензии и привязка HWID при первой активации (для лоадера)
        success, message, data = await authenticate(
            key=key,
            hwid=hwid,
            ip=client_ip
        )

    response_dict = {
        "status": "ok" if success else "error",
        "message": message,
        "key": data.get("key", ""),
        "expires_at": data.get("expires_at", ""),
        "days_left": data.get("days_left", 0)
    }

    if is_encrypted:
        enc_response = encrypt_payload(json.dumps(response_dict), password=SERVER_SECRET)
        return {"data": enc_response}

    return response_dict


@app.post("/api/v1/ping")
async def api_ping(req: RawAuthRequest, request: Request):
    """
    Эндпоинт периодического пингования (heartbeat) из чита.
    Проверяет валидность подписки по HWID или ключу без повторной активации и записи в логи auth_logs.
    """
    is_encrypted, payload = extract_payload(req)
    if payload is None:
        err_dict = {"status": "error", "message": "DECRYPTION_FAILED"}
        if is_encrypted:
            return {"data": encrypt_payload(json.dumps(err_dict), password=SERVER_SECRET)}
        return err_dict

    key = (payload.get("key") or "").strip()
    hwid = (payload.get("hwid") or "").strip()

    if not key and hwid:
        valid, reason, data = await verify_hwid_subscription(hwid)
    else:
        valid, reason = await verify_license(key, hwid)
        data = {}

    response_dict = {
        "status": "ok" if valid else "error",
        "message": reason,
        "expires_at": data.get("expires_at", ""),
        "days_left": data.get("days_left", 0)
    }

    if is_encrypted:
        return {"data": encrypt_payload(json.dumps(response_dict), password=SERVER_SECRET)}
    return response_dict


@app.post("/api/v1/cheats/list")
async def list_cheats(req: RawAuthRequest, request: Request):
    """
    Возвращает список доступных читов/модулей из папки cheat/ на сервере.
    Требует валидную лицензию и совпадение HWID.
    """
    is_encrypted, payload = extract_payload(req)
    if payload is None:
        err_dict = {"status": "error", "message": "DECRYPTION_FAILED"}
        return {"data": encrypt_payload(json.dumps(err_dict), password=SERVER_SECRET)}

    key = (payload.get("key") or "").strip()
    hwid = (payload.get("hwid") or "").strip()

    valid, reason = await verify_license(key, hwid)
    if not valid:
        err_dict = {"status": "error", "message": reason, "cheats": []}
        if is_encrypted:
            return {"data": encrypt_payload(json.dumps(err_dict), password=SERVER_SECRET)}
        return err_dict

    # Сканируем папку CHEATS_DIR
    cheats_list = []
    if os.path.isdir(CHEATS_DIR):
        for item in sorted(os.listdir(CHEATS_DIR)):
            item_path = os.path.join(CHEATS_DIR, item)
            if os.path.isfile(item_path):
                # Исключаем скрытые и временные файлы
                if item.startswith(".") or item.endswith(".tmp"):
                    continue
                size = os.path.getsize(item_path)
                cheats_list.append({"name": item, "size": size})

    res = {
        "status": "ok",
        "cheats": cheats_list
    }

    if is_encrypted:
        return {"data": encrypt_payload(json.dumps(res), password=SERVER_SECRET)}
    return res


@app.post("/api/v1/cheats/download")
async def download_cheat(req: RawAuthRequest, request: Request):
    """
    Скачивание файла чита/модуля из папки cheat/.
    Требует валидную лицензию, совпадение HWID и безопасное имя файла.
    """
    is_encrypted, payload = extract_payload(req)
    if payload is None:
        raise HTTPException(status_code=400, detail="DECRYPTION_FAILED")

    key = (payload.get("key") or "").strip()
    hwid = (payload.get("hwid") or "").strip()
    filename = (payload.get("filename") or "").strip()

    valid, reason = await verify_license(key, hwid)
    if not valid:
        raise HTTPException(status_code=403, detail=f"ACCESS_DENIED: {reason}")

    if not filename:
        raise HTTPException(status_code=400, detail="MISSING_FILENAME")

    # Защита от Path Traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.abspath(os.path.join(CHEATS_DIR, safe_filename))

    if not file_path.startswith(CHEATS_DIR) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/octet-stream"
    )
