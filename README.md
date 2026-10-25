# SWIPET — «Тиндер для животных»

Сервис подбора домашних животных: свайпы, умная лента на ИИ (ruBERT), объяснение «почему мне это показали» (GigaChat), чат покупателя и продавца, объявления с фото, подписка.

```
backend/    FastAPI + SQLAlchemy (SQLite или PostgreSQL), ruBERT, GigaChat
frontend/   React + Vite
setup.bat   установка всего одной командой (один раз)
start.bat   запуск бэкенда и фронтенда одной командой
reset_db.bat  пересоздать тестовую базу
```

## Что нужно на компьютере

- **Python 3.11–3.13** (python.org, при установке галочка «Add python.exe to PATH»)
- **Node.js LTS** (nodejs.org)
- Интернет при первой установке: библиотеки, модель ruBERT (~1,7 ГБ), фото питомцев

## Запуск на Windows

1. **Один раз:** двойной клик по `setup.bat` (или в терминале `.\setup.bat`). Он:
   создаёт `backend\venv` и ставит библиотеки → создаёт `backend\.env` из `.env.example` →
   скачивает фото питомцев → создаёт тестовую базу `backend\dev.db` → считает векторы ruBERT → `npm install` во фронтенде.
2. Впишите ключ GigaChat в `backend\.env`: строка `GIGACHAT_KEY=...` (без ключа всё работает, но объяснения будут по шаблону).
3. **Каждый раз:** двойной клик по `start.bat`. Откроются два окна (бэкенд :8000 и фронтенд :5173) и браузер на http://localhost:5173.
   Остановить — закрыть эти два окна.

Тестовые аккаунты (пароль `demo1234`): `koshatnik@example.com` — покупатель, `maria@example.com` — продавец Мурки, Барсика и Пушка.

## Запуск вручную (любая ОС)

```
# терминал 1
cd backend
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
copy .env.example .env           # macOS/Linux: cp .env.example .env ; затем вписать GIGACHAT_KEY
python download_photos.py
python seed.py
python build_vectors.py
uvicorn main:app --reload        # http://127.0.0.1:8000/docs

# терминал 2
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

## Документация

- `backend/ARCHITECTURE.md` — как всё устроено: ИИ (ruBERT, GigaChat), лента, вход, чат, фото, база
- `backend/README_reco.md` — эндпоинты рекомендаций и проверки (`check_reco.py`, `demo.py`)
- `frontend/README.md` — фронтенд
- Фото питомцев: Unsplash License (бесплатно, без обязательного указания автора), источники — `backend/seed_photos/photos.json`
