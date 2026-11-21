ALTER TABLE games DROP CONSTRAINT IF EXISTS games_game_type_check;
ALTER TABLE games
    ADD CONSTRAINT games_game_type_check
    CHECK (game_type IN ('chess', 'checkers', 'poker', 'uno', 'durak', 'blackjack', 'preferans', 'go', 'domino'));

ALTER TABLE user_settings DROP CONSTRAINT IF EXISTS user_settings_default_game_check;
ALTER TABLE user_settings
    ADD CONSTRAINT user_settings_default_game_check
    CHECK (default_game IN ('chess', 'checkers', 'uno', 'poker', 'durak', 'blackjack', 'preferans', 'go', 'domino'));

ALTER TABLE site_settings
    ADD COLUMN IF NOT EXISTS domino_open BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE news_posts DROP CONSTRAINT IF EXISTS news_posts_cover_check;
ALTER TABLE news_posts ADD CONSTRAINT news_posts_cover_check CHECK (
    cover IS NULL
    OR cover IN ('light-theme', 'uno-evening', 'welcome', 'card-games', 'go', 'beta', 'domino')
    OR cover ~ '^[0-9a-f]{32}\.(jpg|png|webp)$'
);

INSERT INTO news_posts (id, title, summary, body, kind, cover, published_on)
VALUES (
    'c3d4e5f6-a7b8-4c9d-8e7f-6a5b4c3d2e1f',
    'В гостиной открылось домино',
    'Двадцать восемь костей, линия на столе и базар. Играйте вдвоём, втроём или вчетвером — с друзьями или с компьютером.',
    $body$<p>С 21 ноября в гостиной есть домино. Шахматы, шашки, го, Уно, покер, дурак, блэкджек и преферанс остаются на своих местах: теперь в доме девять игр.</p>
<h2>Как играют</h2>
<p>Набор double-six: двадцать восемь костей, от пустой до дубля шесть. Двое получают по семь костей, трое и четверо — по пять. Остальное лежит в базаре.</p>
<p>Первым ходит тот, у кого старший дубль, и кладёт его на стол. Если дублей нет, ходит обладатель старшей кости. Дальше кость ставят к открытому концу с тем же числом. Нет подходящей — берут из базара, пока не появится ход или базар не кончится. Тогда пас.</p>
<p>Кто первым выложил все кости, выиграл. Если пас обошёл стол, это рыба: победа у того, у кого меньше очков. Одинаковая меньшая сумма — ничья. Фишки начисляются за победу и ничью, как в остальных играх без банка. Денег на столе нет.</p>
<p>Партию можно собрать с человеком по коду или с компьютером. За столом от двух до четырёх мест. Часов на партию нет.</p>
<p>Подробности — в <a href="/rules#domino">правилах гостиной</a>.</p>$body$,
    'update',
    'domino',
    DATE '2026-11-21'
)
ON CONFLICT (id) DO NOTHING;
