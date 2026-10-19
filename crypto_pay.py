import aiohttp
from typing import Optional, Dict, Any
from .config import CRYPTO_PAY_TOKEN, CRYPTO_PAY_API_URL


class CryptoPayClient:
    """Клиент для взаимодействия с официальным API @CryptoBot (Crypto Pay)"""

    def __init__(self, token: str = CRYPTO_PAY_TOKEN, base_url: str = CRYPTO_PAY_API_URL):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Crypto-Pay-API-Token": self.token,
            "User-Agent": "VortexBot/1.0",
            "Content-Type": "application/json"
        }

    async def get_me(self) -> Optional[Dict[str, Any]]:
        """Проверка валидности токена приложения"""
        url = f"{self.base_url}/getMe"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result")
        except Exception:
            pass
        return None

    async def create_invoice(
        self,
        amount: int,
        days: int,
        user_id: int,
        fiat: str = "RUB",
        expires_in: int = 3600
    ) -> Optional[Dict[str, Any]]:
        """
        Создает инвойс на оплату в CryptoBot.
        Сумма указывается в рублях (RUB), а пользователь может оплатить любой поддерживаемой криптовалютой
        (USDT, TON, BTC, ETH, SOL, TRX, LTC, BNB и др.) с автоматической конвертацией.
        """
        url = f"{self.base_url}/createInvoice"
        payload = f"{user_id}:{days}:{amount}"
        body = {
            "amount": str(amount),
            "currency_type": "fiat",
            "fiat": fiat,
            "description": f"Лицензия Vortex Loader на {days} дн.",
            "hidden_message": f"Спасибо за покупку! Ваш ключ на {days} дн. сгенерирован.",
            "payload": payload,
            "expires_in": expires_in
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=body, headers=self.headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result")
        except Exception:
            pass
        return None

    async def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Получает текущий статус инвойса по его ID"""
        url = f"{self.base_url}/getInvoices?invoice_ids={invoice_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("result", {}).get("items", [])
                        return items[0] if items else None
        except Exception:
            pass
        return None


# Экземпляр клиента по умолчанию
crypto_pay = CryptoPayClient()

