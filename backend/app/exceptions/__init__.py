class TokenInvalidoException(Exception):
    def __init__(self) -> None:
        super().__init__("Token inválido ou expirado.")
