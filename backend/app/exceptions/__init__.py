class CredencialJaCadastradaException(Exception):
    def __init__(self, credencial_institucional: str) -> None:
        self.credencial_institucional = credencial_institucional
        super().__init__(
            f"Credencial institucional '{credencial_institucional}' já cadastrada."
        )


class CredenciaisInvalidasException(Exception):
    def __init__(self) -> None:
        super().__init__("Credenciais inválidas.")


class TokenInvalidoException(Exception):
    def __init__(self) -> None:
        super().__init__("Token inválido ou expirado.")


class PerfilInsuficienteException(Exception):
    def __init__(self) -> None:
        super().__init__("Perfil insuficiente para este recurso.")
