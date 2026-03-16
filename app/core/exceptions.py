class AppError(Exception):
    """Base de errores del proyecto."""


class ConfigurationError(AppError):
    """Configuracion invalida o incompleta."""


class UnsupportedTargetError(AppError):
    """La fuente no soporta el target solicitado."""


class FetchError(AppError):
    """Error al descargar contenido de una fuente."""


class ParsingError(AppError):
    """Error al parsear contenido HTML/XML."""


class SelectorDriftError(ParsingError):
    """La estructura de la fuente cambio y los selectores dejaron de encajar."""


class RobotsPolicyError(FetchError):
    """La politica de robots no permite solicitar una URL."""


class InvalidStateTransitionError(AppError):
    """La transicion de estado solicitada no es valida."""
