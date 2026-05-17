CENTRAL_CONTENT_SELECTOR = "#contenedorCentral"
TOURNAMENT_HEADER_SELECTOR = "#cabeceraTorneo"
CALENDAR_HEADING_SELECTOR = ".contenedorTitularTorneoCalendario"
MATCH_CARD_SELECTOR = ".cajaPartido"
STANDINGS_TABLE_SELECTOR = "#latabla"
STANDINGS_ROW_SELECTOR = "#latabla tr"

MATCH_HOME_SELECTOR = ".equipoPartidoLocal"
MATCH_AWAY_SELECTOR = ".equipoPartidoVisitante"
MATCH_SCORE_SELECTOR = ".resultadoPartido"
MATCH_TIME_SELECTOR = ".horaPartido"
MATCH_PLANNED_TIME_SELECTOR = ".horaPrevistaPartido"
MATCH_DETAIL_LINK_SELECTOR = "a[href*='/resultados-directo/partido/']"
# NOTE: Half-time score selector — needs verification against live match detail pages.
# futbolme.com typically renders the half-time score inside a ".marcadorDescanso" element
# with text like "Descanso 1-0", or as a dedicated score row within ".infoPartido".
# The selector below targets the most common pattern observed in Spanish football sites;
# if not found, the parser returns None for both halftime fields (safe fallback).
MATCH_HALFTIME_SCORE_SELECTOR = ".marcadorDescanso"

MATCH_EVENT_TABLE_SELECTOR = "table.col-12"
MATCH_EVENT_PERIOD_HEADING_SELECTOR = "h3.subtitulo"
MATCH_EVENT_MINUTE_SELECTOR = ".label.label-info"
MATCH_EVENT_PLAYER_LINK_SELECTOR = "a[href*='/jugador.php']"
MATCH_EVENT_GOAL_ICON_SELECTOR = "img[src*='balon']"
