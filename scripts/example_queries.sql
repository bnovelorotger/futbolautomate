-- Ultimos resultados
SELECT
  c.code AS competition_code,
  m.round_name,
  m.match_date,
  m.match_time,
  m.home_team_raw,
  m.home_score,
  m.away_score,
  m.away_team_raw
FROM matches m
JOIN competitions c ON c.id = m.competition_id
WHERE c.code = 'division_honor_mallorca'
  AND m.status = 'finished'
ORDER BY m.match_date DESC, m.match_time DESC, m.id DESC
LIMIT 10;

-- Clasificacion actual
SELECT
  c.code AS competition_code,
  s.position,
  s.team_raw,
  s.points,
  s.played,
  s.wins,
  s.draws,
  s.losses,
  s.goals_for,
  s.goals_against,
  s.goal_difference
FROM standings s
JOIN competitions c ON c.id = s.competition_id
WHERE c.code = 'division_honor_mallorca'
ORDER BY s.position ASC;

-- Proximos partidos
SELECT
  c.code AS competition_code,
  m.round_name,
  m.match_date,
  m.match_time,
  m.home_team_raw,
  m.away_team_raw,
  m.status
FROM matches m
JOIN competitions c ON c.id = m.competition_id
WHERE c.code = 'division_honor_mallorca'
  AND m.status = 'scheduled'
ORDER BY m.match_date ASC, m.match_time ASC, m.id ASC
LIMIT 10;

-- Partidos por jornada
SELECT
  c.code AS competition_code,
  m.round_name,
  m.match_date,
  m.match_time,
  m.home_team_raw,
  m.home_score,
  m.away_score,
  m.away_team_raw,
  m.status
FROM matches m
JOIN competitions c ON c.id = m.competition_id
WHERE c.code = 'division_honor_mallorca'
  AND m.round_name = 'Jornada 25'
ORDER BY m.match_date ASC, m.match_time ASC, m.id ASC;

-- Equipos con mas goles a favor
SELECT
  s.position,
  s.team_raw,
  s.goals_for
FROM standings s
JOIN competitions c ON c.id = s.competition_id
WHERE c.code = 'division_honor_mallorca'
ORDER BY s.goals_for DESC, s.position ASC
LIMIT 5;

-- Equipos con menos goles en contra
SELECT
  s.position,
  s.team_raw,
  s.goals_against
FROM standings s
JOIN competitions c ON c.id = s.competition_id
WHERE c.code = 'division_honor_mallorca'
ORDER BY s.goals_against ASC, s.position ASC
LIMIT 5;

-- Equipos con mas victorias
SELECT
  s.position,
  s.team_raw,
  s.wins
FROM standings s
JOIN competitions c ON c.id = s.competition_id
WHERE c.code = 'division_honor_mallorca'
ORDER BY s.wins DESC, s.position ASC
LIMIT 5;

-- Resumen agregado
WITH team_counts AS (
  SELECT competition_id, COUNT(*) AS total_teams
  FROM standings
  GROUP BY competition_id
)
SELECT
  c.code AS competition_code,
  COALESCE(tc.total_teams, 0) AS total_teams,
  COUNT(*) AS total_matches,
  COUNT(*) FILTER (WHERE m.status = 'finished') AS played_matches,
  COUNT(*) FILTER (WHERE m.status <> 'finished') AS pending_matches
FROM matches m
JOIN competitions c ON c.id = m.competition_id
LEFT JOIN team_counts tc ON tc.competition_id = c.id
WHERE c.code = 'division_honor_mallorca'
GROUP BY c.code, tc.total_teams;

-- Ultimas noticias
SELECT
  source_name,
  published_at,
  title,
  source_url
FROM news
ORDER BY published_at DESC NULLS LAST, id DESC
LIMIT 10;

-- Noticias de hoy en Europe/Madrid
SELECT
  source_name,
  published_at,
  title
FROM news
WHERE published_at >= TIMESTAMPTZ '2026-03-14 00:00:00+01:00'
  AND published_at < TIMESTAMPTZ '2026-03-15 00:00:00+01:00'
ORDER BY published_at DESC, id DESC;

-- Noticias por fuente
SELECT
  source_name,
  published_at,
  title
FROM news
WHERE source_name = 'diario_mallorca'
ORDER BY published_at DESC NULLS LAST, id DESC
LIMIT 10;

-- Busqueda simple por titular
SELECT
  source_name,
  published_at,
  title
FROM news
WHERE lower(title) LIKE '%mallorca%'
ORDER BY published_at DESC NULLS LAST, id DESC
LIMIT 10;

-- Noticias editoriales relevantes para futbol balear
SELECT
  n.source_name,
  n.published_at,
  n.title,
  ne.clubs_detected,
  ne.competition_detected,
  ne.editorial_relevance_score
FROM news n
JOIN news_enrichments ne ON ne.news_id = n.id
WHERE ne.is_football = true
  AND ne.is_balearic_related = true
ORDER BY ne.editorial_relevance_score DESC, n.published_at DESC NULLS LAST
LIMIT 20;

-- Noticias editoriales por club
SELECT
  n.source_name,
  n.published_at,
  n.title,
  ne.clubs_detected,
  ne.editorial_relevance_score
FROM news n
JOIN news_enrichments ne ON ne.news_id = n.id
WHERE ne.clubs_detected::text ILIKE '%Real Mallorca%'
ORDER BY ne.editorial_relevance_score DESC, n.published_at DESC NULLS LAST
LIMIT 20;

-- Resumen editorial agregado
SELECT
  COUNT(*) FILTER (WHERE ne.is_football = true AND ne.is_balearic_related = true) AS relevant_balearic_football,
  COUNT(*) FILTER (WHERE ne.is_football = true AND ne.is_balearic_related = false) AS football_non_balearic,
  COUNT(*) FILTER (WHERE ne.is_football = false) AS other_sports_or_unknown
FROM news_enrichments ne;
