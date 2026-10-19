"""
Модуль криптографии для защиты данных между C++ лоадером и сервером.
Совместим с decryptor.py и Windows Cryptography Next Generation (CNG / bcrypt.dll):
- PBKDF2-HMAC-SHA256 (1000 итераций, 32 байта)
- AES-256 в режиме CBC с PKCS7 паддингом
- Формат: Salt(16) + IV(16) + Ciphertext в виде Hex-строки
"""
from typing import Optional
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from .config import CIPHER_SECRET


def encrypt_data(plain_text: str, password: str = CIPHER_SECRET) -> str:
    """Шифрует строку и возвращает Hex-строку структуры: Salt + IV + Ciphertext"""
    password_bytes = password.encode('utf-8')
    plain_bytes = plain_text.encode('utf-8')
    
    salt = get_random_bytes(16)
    iv = get_random_bytes(16)
    
    key = PBKDF2(password_bytes, salt, dkLen=32, count=1000, hmac_hash_module=SHA256)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plain_bytes, AES.block_size))
    
    full_bytes = salt + iv + ciphertext
    return full_bytes.hex()


def decrypt_data(hex_str: str, password: str = CIPHER_SECRET) -> Optional[str]:
    """
    Расшифровывает Hex-строку структуры: Salt + IV + Ciphertext.
    Возвращает расшифрованную строку либо None при ошибке/неверном ключе/паддинге.
    """
    try:
        full_bytes = bytes.fromhex(hex_str.strip())
        password_bytes = password.encode('utf-8')
        
        if len(full_bytes) < 48:
            return None
            
        salt = full_bytes[:16]          
        iv = full_bytes[16:32]         
        ciphertext = full_bytes[32:]   
        
        key = PBKDF2(password_bytes, salt, dkLen=32, count=1000, hmac_hash_module=SHA256)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_bytes = unpad(cipher.decrypt(ciphertext), AES.block_size)
        
        return decrypted_bytes.decode('utf-8')
    except Exception:
        return None


# Алиасы функций
encrypt_payload = encrypt_data
decrypt_payload = decrypt_data
