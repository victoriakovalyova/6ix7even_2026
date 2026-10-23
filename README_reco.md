# Рекомендации и подписка

Лента питомцев по смыслу описаний (векторы на базе ruBERT от Сбера) и правилам
(вид, город, возраст, лайки), лимит свайпов и рекламные слоты по подписке.

## Запуск на SQLite (без Postgres)
1. python -m venv venv, затем venv\Scripts\activate
2. pip install -r requirements_reco.txt
3. В .env: DATABASE_URL=sqlite:///./dev.db и EMBED_BACKEND=sbert
   (database.py должен брать адрес из DATABASE_URL, если она задана)
4. python seed.py  (загрузить тестовые данные)
5. python play_db.py all  (ленты для тестовых пользователей)
6. python play_db.py 4  (интерактивная лента, 4 = тестовый пользователь)

При первом запуске модель скачивается (около 2 ГБ).
python seed.py reset сбрасывает счётчики свайпов и премиум клиентов.

## Файлы
- embedders.py: текст в вектор
- reco_vectors.py: векторы питомцев и вкус пользователя
- reco_feed.py: гибридная лента
- monetization.py: премиум, лимит свайпов, рекламные слоты
- demo_data.py: тестовые питомцы и описания (временно, пока нет поля description)
- seed.py: тестовые данные; play_db.py: проверка ленты