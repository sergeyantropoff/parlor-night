UPDATE news_posts
SET
    title = replace(title, 'UNO', 'Уно'),
    summary = replace(summary, 'UNO', 'Уно'),
    body = replace(body, 'UNO', 'Уно')
WHERE title LIKE '%UNO%'
   OR summary LIKE '%UNO%'
   OR body LIKE '%UNO%';
