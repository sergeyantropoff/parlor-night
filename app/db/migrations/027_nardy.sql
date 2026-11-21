ALTER TABLE games DROP CONSTRAINT IF EXISTS games_game_type_check;
ALTER TABLE games
    ADD CONSTRAINT games_game_type_check
    CHECK (game_type IN ('chess', 'checkers', 'poker', 'uno', 'durak', 'blackjack', 'preferans', 'go', 'domino', 'nardy'));

ALTER TABLE user_settings DROP CONSTRAINT IF EXISTS user_settings_default_game_check;
ALTER TABLE user_settings
    ADD CONSTRAINT user_settings_default_game_check
    CHECK (default_game IN ('chess', 'checkers', 'uno', 'poker', 'durak', 'blackjack', 'preferans', 'go', 'domino', 'nardy'));

ALTER TABLE site_settings
    ADD COLUMN IF NOT EXISTS nardy_open BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE news_posts DROP CONSTRAINT IF EXISTS news_posts_cover_check;
ALTER TABLE news_posts ADD CONSTRAINT news_posts_cover_check CHECK (
    cover IS NULL
    OR cover IN ('light-theme', 'uno-evening', 'welcome', 'card-games', 'go', 'beta', 'domino', 'nardy')
    OR cover ~ '^[0-9a-f]{32}\.(jpg|png|webp)$'
);

INSERT INTO news_posts (id, title, summary, body, kind, cover, published_on)
VALUES (
    'd4e5f6a7-b8c9-4d0e-9f8a-7b6c5d4e3f21',
    'В гостиной открылись нарды',
    'Длинные и короткие нарды на одной доске. Шашки ходят плавно, кости крутятся, а в коротких можно удваивать.',
    $body$<p>С 22 ноября в гостиной можно играть в нарды. Шахматы, шашки, го, домино, Уно, покер, дурак, блэкджек и преферанс остаются на своих местах: теперь в доме десять игр.</p>
<h2>Две игры, одна доска</h2>
<p>Перед партией выбирают длинные или короткие нарды. В длинных оба идут вперёд по своему кругу: чужое поле закрыто даже одной шашкой, с головы за ход снимают одну, а в первый ход — две. Шесть полей четверти нельзя закрыть, пока соперник их не прошёл. Счёт — оин, марс и кокс.</p>
<p>В коротких шашка бьёт одиночную и отправляет её на бар. Сначала входят с бара. Если можно сыграть обе кости, играются обе; если только одна — большую. Дубль даёт четыре хода. Снимать можно, когда все свои шашки в доме. Куб удвоения есть только в коротких: его предлагают до броска, соперник принимает или сдаёт партию по текущей ставке. Гэммон и бэкгэммон умножают ставку.</p>
<p>Партию собирают с человеком по коду или с компьютером. У компьютера те же пять уровней, что и в других играх. Часов нет. Фишки начисляются за победу, денег на столе нет.</p>
<p>Подробности — в <a href="/rules#nardy">правилах гостиной</a>.</p>$body$,
    'update',
    'nardy',
    DATE '2026-11-22'
)
ON CONFLICT (id) DO NOTHING;
