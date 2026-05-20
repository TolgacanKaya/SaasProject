from cryptography.fernet import Fernet
from django.conf import settings
import base64

def get_cipher():
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        # Fallback for development if key is missing, but should always be present in prod
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)

def encrypt_data(plain_text):
    """Veriyi şifreler. Girdi None ise None döner."""
    if plain_text is None:
        return None
    cipher = get_cipher()
    if not cipher:
        return plain_text
    
    return cipher.encrypt(str(plain_text).encode()).decode()

def decrypt_data(cipher_text):
    """Şifreli veriyi çözer. Hata durumunda veya None ise orijinali döner."""
    if not cipher_text:
        return cipher_text
    cipher = get_cipher()
    if not cipher:
        return cipher_text
    
    try:
        return cipher.decrypt(cipher_text.encode() if isinstance(cipher_text, str) else cipher_text).decode()
    except Exception:
        # Şifreli değilse veya anahtar yanlışsa ham veriyi dön (Geriye dönük uyumluluk için)
        return cipher_text
