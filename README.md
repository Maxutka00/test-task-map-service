GET /api/auth/csrf/ - отримання CSRF-токена  
POST /api/auth/register/ - реєстрація користувача (username, email, password)  
POST /api/auth/login/ - вхід у систему (username, password)  
POST /api/auth/logout/ - вихід із системи  
POST /api/auth/password/reset/ - запит листа для скидання пароля (email)  
POST /api/auth/password/reset/confirm/ - встановлення нового пароля (uid, token, password)  

GET /api/categories/ - список категорій  
POST /api/categories/ - створення категорії (name, тільки адмін)  
GET /api/categories/{id}/ - деталі категорії  
PUT/PATCH /api/categories/{id}/ - оновлення категорії (тільки адмін)  
DELETE /api/categories/{id}/ - видалення вільної категорії (тільки адмін)  

GET /api/locations/ - список локацій (search, category, author, rating, min_rating, max_rating, ordering, page)  
POST /api/locations/ - створення локації (title, description, category, address, latitude, longitude)  
GET /api/locations/{id}/ - деталі локації та облік перегляду  
PUT/PATCH /api/locations/{id}/ - оновлення локації (автор або адмін)  
DELETE /api/locations/{id}/ - м'яке видалення локації (автор або адмін)  
GET /api/locations/export/?format=json|csv - експорт локацій у JSON або CSV  
PUT /api/locations/{id}/subscription/ - підписка на сповіщення про нові відгуки  
DELETE /api/locations/{id}/subscription/ - відписка від сповіщень  

GET /api/locations/{id}/reviews/ - список відгуків локації  
POST /api/locations/{id}/reviews/ - створення відгуку (rating 1-5, comment)  
DELETE /api/reviews/{id}/ - видалення відгуку (автор або адмін)  
PUT /api/reviews/{id}/vote/ - оцінка відгуку (value: like або dislike)  
DELETE /api/reviews/{id}/vote/ - скасування своєї оцінки відгуку  
