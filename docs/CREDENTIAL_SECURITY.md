# Credential Security

## Архитектура

```
OAuth callback / Save credentials
  credentials (dict)  ──►  encrypt_credentials()  ──►  ciphertext (str)

Sync / Upload / Download
  ciphertext  ──►  decrypt_credentials()  ──►  dict  ──►  API

Key: SECURITY_ENCRYPTION_KEY (Fernet, base64-encoded 32 bytes)
Cipher: AES-128-CBC + HMAC-SHA256 (Fernet)
```

Credentials (Zoom, YouTube, VK) шифруются через `api/auth/encryption.py`:

- **`SECURITY_ENCRYPTION_KEY`** — обязательный Fernet-ключ (base64, 32 байта)
- **`SECURITY_ENCRYPTION_KEY_OLD`** — опциональный предыдущий ключ (для ротации)

Генерация ключа:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Как работает расшифровка

`decrypt_credentials` пробует ключи по порядку: primary → old. Первый успешный — возвращает результат.

`needs_reencrypt` пробует расшифровать только primary ключом. Если не получается — данные на старом ключе, нужна перешифровка. `CredentialService` делает это автоматически при чтении (lazy re-encrypt).

## Ротация ключей

1. Сгенерировать новый Fernet-ключ (команда выше).
2. В `.env`:
   ```
   SECURITY_ENCRYPTION_KEY=<новый ключ>
   SECURITY_ENCRYPTION_KEY_OLD=<старый ключ>
   ```
3. Перезапустить API + Celery.
4. Запустить миграцию:
   ```bash
   uv run python scripts/reencrypt_credentials.py --dry-run  # проверка
   uv run python scripts/reencrypt_credentials.py             # выполнение
   ```
5. Убрать `SECURITY_ENCRYPTION_KEY_OLD`.

Lazy re-encrypt в `CredentialService` — страховка на время между шагами 3 и 4.

## Troubleshooting: InvalidToken

Данные зашифрованы одним ключом, приложение пытается расшифровать другим.

| Ситуация | Описание |
|----------|----------|
| **Разные процессы** | API и Celery загружают `.env` по-разному |
| **Ротация без миграции** | Изменили ключ, не задали `_OLD`, не запустили скрипт |
| **Разные окружения** | Локально один `.env`, в Docker — другой |

### Решение 1: Ротация с сохранением старого ключа

См. раздел «Ротация ключей» выше.

### Решение 2: Переподключить аккаунты

Старый ключ потерян:

1. В UI: **Settings → Credentials** — удалить credential
2. Пройти OAuth заново

## Production checklist

- [ ] `APP_DEBUG=false`
- [ ] `SECURITY_JWT_SECRET_KEY` — не дефолтный
- [ ] `SECURITY_ENCRYPTION_KEY` — задан (обязателен)
- [ ] API и Celery получают одинаковые env
